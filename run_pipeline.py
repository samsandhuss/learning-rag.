"""
Learning notes -> ChromaDB -> retrieval demo.

One command:  python run_pipeline.py
It loads the notes in ./notes, splits them into chunks, embeds each chunk,
stores them in a local ChromaDB, runs test questions, scores retrieval,
and opens report.html in your browser.

Ask your own question:  python run_pipeline.py --ask "what is ALCOA+?"
Use a neural embedding model (needs internet once to download it):
                        python run_pipeline.py --embed minilm
"""
import argparse, html, json, pathlib, re, shutil, time, webbrowser

import chromadb
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.manifold import TSNE
from sklearn.feature_extraction.text import TfidfVectorizer

HERE = pathlib.Path(__file__).parent
NOTES, DB, REPORT = HERE / "notes", HERE / "chroma_db", HERE / "report.html"
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]


# ---------- Step 1: load ----------
def load_notes():
    docs = []
    for p in sorted(NOTES.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        body = " ".join(l for l in text.splitlines()[1:] if l.strip())
        docs.append({"file": p.name, "title": title, "body": body})
    return docs


# ---------- Step 2: chunk ----------
def chunk(doc, size=2, overlap=1):
    """Groups of `size` sentences, sliding by size-overlap so ideas aren't cut in half."""
    sents = re.split(r"(?<=[.!?])\s+", doc["body"])
    step, out = size - overlap, []
    for i in range(0, max(len(sents) - overlap, 1), step):
        out.append(" ".join(sents[i:i + size]))
    return out


# ---------- Step 3: embed ----------
class LSAEmbedder:
    """Offline embeddings: TF-IDF word weights compressed to 64 dense dimensions (LSA).
    No download needed. Swap for --embed minilm to use a real neural model."""

    def fit(self, texts):
        self.tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        X = self.tfidf.fit_transform(texts)
        self.svd = TruncatedSVD(n_components=min(64, X.shape[0] - 1), random_state=0).fit(X)
        self.name = f"LSA (TF-IDF + SVD, {self.svd.n_components} dims, offline, no download)"
        return self

    def __call__(self, texts):
        v = self.svd.transform(self.tfidf.transform(texts))
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
        return v.tolist()


class MiniLMEmbedder:
    name = "all-MiniLM-L6-v2 (384 dims, neural)"

    def fit(self, texts):
        from chromadb.utils import embedding_functions
        self.ef = embedding_functions.DefaultEmbeddingFunction()
        return self

    def __call__(self, texts):
        return [list(map(float, v)) for v in self.ef(texts)]


# ---------- Step 4: store ----------
def build_store(chunks, embedder):
    if DB.exists():
        shutil.rmtree(DB)
    client = chromadb.PersistentClient(path=str(DB))
    col = client.create_collection("learning_notes", metadata={"hnsw:space": "cosine"})
    vecs = embedder([c["text"] for c in chunks])
    col.add(ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[{"source": c["file"], "title": c["title"]} for c in chunks],
            embeddings=vecs)
    return col, np.array(vecs)


# ---------- Step 5: retrieve + evaluate ----------
def search(col, embedder, q, k=3):
    r = col.query(query_embeddings=embedder([q]), n_results=k)
    return [{"text": d, "source": m["source"], "title": m["title"], "score": 1 - dist}
            for d, m, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])]


def evaluate(col, embedder, tests, k=3):
    rows = []
    for t in tests:
        hits = search(col, embedder, t["q"], k)
        rank = next((i + 1 for i, h in enumerate(hits) if h["source"] == t["expect"]), None)
        rows.append({**t, "hits": hits, "rank": rank})
    hit = sum(r["rank"] is not None for r in rows) / len(rows)
    mrr = sum(1 / r["rank"] for r in rows if r["rank"]) / len(rows)
    return rows, hit, mrr


# ---------- Step 6: report ----------
def scatter(vecs, chunks, files, qvecs, qlabels):
    allv = np.vstack([vecs, qvecs])
    xy = TSNE(n_components=2, perplexity=8, metric="cosine", init="random", random_state=0).fit_transform(allv)
    lo, hi = xy.min(0), xy.max(0)
    W, H, P = 640, 360, 24
    pt = lambda p: (P + (p[0] - lo[0]) / (hi[0] - lo[0] + 1e-9) * (W - 2 * P),
                    H - P - (p[1] - lo[1]) / (hi[1] - lo[1] + 1e-9) * (H - 2 * P))
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Map of chunk embeddings">']
    for (x, y), c in zip(map(pt, xy[:len(chunks)]), chunks):
        col = COLOURS[files.index(c["file"]) % len(COLOURS)]
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{col}" stroke="var(--surface)" stroke-width="2">'
                 f'<title>{html.escape(c["title"])}: {html.escape(c["text"][:140])}…</title></circle>')
    for (x, y), lab in zip(map(pt, xy[len(chunks):]), qlabels):
        s.append(f'<g><path d="M{x-6:.1f},{y:.1f}h12M{x:.1f},{y-6:.1f}v12" stroke="var(--ink)" stroke-width="2"/>'
                 f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="transparent"><title>Question: {html.escape(lab)}</title></circle></g>')
    s.append("</svg>")
    return "".join(s)


def write_report(docs, chunks, embedder, vecs, rows, hit, mrr, secs, asked):
    files = [d["file"] for d in docs]
    title_of = {d["file"]: d["title"] for d in docs}
    legend = "".join(f'<span><i style="background:{COLOURS[i % len(COLOURS)]}"></i>{html.escape(d["title"])}</span>'
                     for i, d in enumerate(docs)) + '<span><b class="plus">+</b>A test question</span>'
    qs = [r["q"] for r in rows] + ([asked["q"]] if asked else [])
    svg = scatter(vecs, chunks, files, np.array(embedder(qs)), qs)

    def hits_html(hits, expect=None):
        out = []
        for i, h in enumerate(hits, 1):
            ok = " ok" if h["source"] == expect else ""
            out.append(f'<div class="hit{ok}"><div class="meta">#{i} · {html.escape(h["title"])} · '
                       f'similarity {h["score"]:.2f}</div>{html.escape(h["text"])}</div>')
        return "".join(out)

    ask_block = ""
    if asked:
        ask_block = (f'<section><span class="step">Your question</span><h2>{html.escape(asked["q"])}</h2>'
                     f'{hits_html(asked["hits"])}</section>')

    table = "".join(
        f'<tr><td>{html.escape(r["q"])}</td><td>{html.escape(title_of[r["expect"]])}</td>'
        f'<td class="{"pass" if r["rank"] else "fail"}">{"✓ rank " + str(r["rank"]) if r["rank"] else "✗ missed"}</td></tr>'
        for r in rows)
    details = "".join(
        f'<details><summary>{html.escape(r["q"])}</summary>{hits_html(r["hits"], r["expect"])}</details>'
        for r in rows)

    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Learning notes in a vector database</title>
<style>
:root{{--bg:#fbfaf7;--surface:#fff;--ink:#1d1c1a;--mut:#6b6862;--line:#e4e1da;--acc:#2a78d6;--ok:#008300;--bad:#c62828}}
@media(prefers-color-scheme:dark){{:root{{--bg:#161615;--surface:#1f1f1d;--ink:#ecebe8;--mut:#9a978f;--line:#2e2d2a;--acc:#3987e5;--ok:#0ca30c;--bad:#ef5350}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:760px;margin:auto;padding:20px 16px 60px}}h1{{font-size:24px;margin:4px 0}}h2{{font-size:17px;margin:2px 0 8px}}
.sub{{color:var(--mut);margin:0 0 12px}}section{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;margin:12px 0}}
.step{{font-size:11px;font-weight:700;color:var(--acc);text-transform:uppercase;letter-spacing:.06em}}
.flow{{display:flex;flex-wrap:wrap;gap:6px;align-items:center}}.flow div{{border:1px solid var(--line);border-radius:8px;padding:8px 10px;flex:1;min-width:100px}}
.flow b{{display:block;font-size:20px}}.flow small{{color:var(--mut)}}
.kpi{{display:flex;gap:10px}}.kpi div{{flex:1;border:1px solid var(--line);border-radius:8px;padding:10px}}.kpi b{{font-size:26px;display:block}}.kpi small{{color:var(--mut)}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;color:var(--mut);margin-bottom:6px}}.legend i{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}}
.plus{{margin-right:5px;color:var(--ink)}}svg{{width:100%;height:auto}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}td,th{{text-align:left;border-top:1px solid var(--line);padding:7px 4px;vertical-align:top}}
.pass{{color:var(--ok);white-space:nowrap}}.fail{{color:var(--bad);white-space:nowrap}}
.hit{{border-left:3px solid var(--line);padding:4px 10px;margin:6px 0;font-size:14px}}.hit.ok{{border-color:var(--ok)}}.meta{{font-size:12px;color:var(--mut)}}
details{{border-top:1px solid var(--line);padding:6px 0}}summary{{cursor:pointer}}
</style></head><body><main>
<span class="step">Personal learning pipeline</span>
<h1>My learning notes, searchable by meaning</h1>
<p class="sub">Notes → chunks → embeddings → ChromaDB → questions → scored results. Ran in {secs:.1f}s on {time.strftime("%d %b %Y %H:%M")}.</p>

<section><span class="step">What the pipeline did</span><div class="flow">
<div><b>{len(docs)}</b><small>notes loaded</small></div>
<div><b>{len(chunks)}</b><small>chunks (2 sentences, 1 overlap)</small></div>
<div><b>{vecs.shape[1]}</b><small>numbers per embedding</small></div>
<div><b>1</b><small>ChromaDB collection, cosine search</small></div></div>
<p class="sub" style="margin-top:8px">Embedding model: {embedder.name}</p></section>

{ask_block}

<section><span class="step">Retrieval quality</span><h2>Does it find the right note?</h2>
<div class="kpi"><div><b>{hit:.0%}</b><small>Hit rate @3: right note in the top 3</small></div>
<div><b>{mrr:.2f}</b><small>Mean reciprocal rank (1.00 = always first)</small></div></div>
<table style="margin-top:10px"><tr><th>Test question</th><th>Should find</th><th>Result</th></tr>{table}</table></section>

<section><span class="step">The vector space</span><h2>Every chunk as a point</h2>
<p class="sub">Each dot is a chunk, squashed from {vecs.shape[1]} dimensions to 2. Similar ideas cluster. Crosses are questions, landing near the notes that answer them. Hover for text.</p>
<div class="legend">{legend}</div>{svg}</section>

<section><span class="step">Under the hood</span><h2>Top 3 chunks per test question</h2>{details}</section>
</main></body></html>"""
    REPORT.write_text(page, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", help="your own question to search the notes with")
    ap.add_argument("--embed", choices=["lsa", "minilm"], default="lsa")
    ap.add_argument("--no-open", action="store_true", help="don't open the browser")
    a = ap.parse_args()
    t0 = time.time()

    docs = load_notes()
    chunks = [{"id": f'{d["file"]}#{i}', "file": d["file"], "title": d["title"], "text": c}
              for d in docs for i, c in enumerate(chunk(d))]
    print(f"1. Loaded {len(docs)} notes  2. Split into {len(chunks)} chunks")

    embedder = (MiniLMEmbedder() if a.embed == "minilm" else LSAEmbedder()).fit([c["text"] for c in chunks])
    col, vecs = build_store(chunks, embedder)
    print(f"3. Embedded with {embedder.name}  4. Stored in ChromaDB at {DB.name}/")

    tests = json.loads((HERE / "questions.json").read_text())
    rows, hit, mrr = evaluate(col, embedder, tests)
    print(f"5. Evaluated {len(tests)} questions: hit@3 = {hit:.0%}, MRR = {mrr:.2f}")

    asked = {"q": a.ask, "hits": search(col, embedder, a.ask)} if a.ask else None
    if asked:
        for h in asked["hits"]:
            print(f'   {h["score"]:.2f}  {h["title"]}: {h["text"][:90]}…')

    write_report(docs, chunks, embedder, vecs, rows, hit, mrr, time.time() - t0, asked)
    print(f"6. Report written to {REPORT.name}")
    if not a.no_open:
        webbrowser.open(REPORT.resolve().as_uri())


if __name__ == "__main__":
    main()
