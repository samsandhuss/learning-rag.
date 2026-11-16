# Evaluating AI systems
Training loss alone can hide overfitting. A model can memorise its training data, so always measure on a held-out validation set it has never seen.
For retrieval, a simple metric is hit rate at k: for a set of test questions with a known correct source, how often does the right source appear in the top k results. Mean reciprocal rank rewards putting it first.
For generated answers, evaluate faithfulness (is it supported by the retrieved context), relevance and correctness. Use golden datasets, human review and LLM-as-judge, and track results over time like regression tests.
Eval quality is about whether the evaluation itself is trustworthy: representative test sets, clear rubrics, agreement between raters and no leakage of test data into training.
