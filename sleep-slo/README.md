# Sleep as a service

A prototype that treats my sleep like a production service, using the same practices a platform team uses to run reliable systems: thresholds, an error budget, an evaluation gate, a vector database, Infrastructure as Code and a CI/CD pipeline.

Every morning it produces a short, plain-English note: am I on track, what went wrong, and what to do differently next month.

> The repo uses **synthetic data only**. Real sleep exports live in `data/real/`, which is git-ignored and never committed. The note is not medical advice: it only compares sleep with targets I set.

## Try it with one button

1. Go to **Actions → sleep-slo → Run workflow**.
2. Set the thresholds: bedtime cut-off, target hours, and the share of good nights.
3. Click **Run workflow**. The morning note and the evaluation results appear on the run page, and the evidence files can be downloaded.

Or locally:

```bash
pip install -r requirements.txt
python sleep_slo.py                                     # synthetic data
python sleep_slo.py --bedtime-cutoff 00:00 --target-hours 7
python sleep_slo.py --data data/real/my_sleep.csv       # your own export
python evals/run_evals.py                               # the evaluation gate
```

## How the reliability ideas map to sleep

| Practice | In a platform team | In this prototype |
|---|---|---|
| **Service Level Indicator** | What you measure, e.g. request latency | Each night: bedtime before the cut-off, and hours asleep at or above target |
| **Service Level Objective** | The target, e.g. 99.9% of requests under 300 ms | 80% of nights in the last 30 days are good nights |
| **Error budget** | How much failure you can afford | 20% of nights can miss (about 6 a month) |
| **Burn rate** | How fast the budget is being used | Bad nights used ÷ bad nights allowed |
| **Budget policy** | Spent budget means reliability work before new features | Spent budget means rest comes first |
| **Evaluation gate** | Tests that must pass before release | 10 cases check the maths, the advice, the tip retrieval and that no medical language appears |
| **Vector database** | Retrieval for search and RAG | ChromaDB returns the most relevant habit tip for the main cause |
| **Audit evidence** | Traceable records for regulated releases | `evidence.json` records the data hash, config, code version and result behind every note |

## What's in here

| Path | What it is |
|---|---|
| `sleep_slo.py` | Service Level Indicators, Service Level Objective, error budget, month comparison, tip retrieval, note and evidence |
| `config.json` | The thresholds |
| `knowledge/` | Habit tips, embedded into ChromaDB at run time |
| `evals/run_evals.py` | The evaluation gate: fails the build if any case fails |
| `make_synthetic_data.py` | Generates the made-up sample data |
| `Dockerfile` | Packages the note. The image won't build if the evaluation gate fails |
| `k8s/` | Kubernetes ConfigMap (thresholds) and CronJob (runs at 07:00 every day) |
| `terraform/` | Infrastructure as Code for the same Kubernetes setup, with mandatory `owner` and `cost-centre` labels |
| `../.github/workflows/sleep-slo.yml` | CI/CD: note → evaluation gate → Terraform validate → container build |

## Run it on Kubernetes (optional)

Needs Docker, [kind](https://kind.sigs.k8s.io/) and Terraform.

```bash
kind create cluster --name sleep
docker build -t sleep-slo:local .
kind load docker-image sleep-slo:local --name sleep
cd terraform && terraform init && terraform apply     # builds namespace, ConfigMap and CronJob
kubectl -n sleep-platform create job --from=cronjob/sleep-morning-note test-run
kubectl -n sleep-platform logs job/test-run            # read the note
terraform destroy                                      # tear it all down
```

## A bug the evaluation gate caught

The first version said 20% of 30 nights allowed 5 bad nights, not 6. In floating point, 0.2 × 30 is 5.999…, which rounded down to 5. The `budget_exact` case failed, the gate blocked it, and the fix was a one-line rounding change. That's what the gate is for.
