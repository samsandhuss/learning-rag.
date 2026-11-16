# How a language model works
A language model predicts the next token. Text is first tokenised into IDs. Each ID is looked up in an embedding table, which turns it into a vector of numbers that captures meaning, plus a position vector.
Attention lets each token look back at earlier tokens. Every head asks a question (query) and earlier tokens offer answers (keys). Attention cost grows with the square of context length.
After attention, each token passes through a small feed-forward network (MLP). In large models most parameters and stored knowledge live in the MLP layers. Mixture-of-Experts replaces one MLP with many and routes each token to a few.
Finally, softmax turns scores into probabilities. Temperature controls how adventurous sampling is: low is safe, high is creative.
My Tiny GPT has 1 layer, 2 heads and about 32k parameters, trained on 20k characters in 40 seconds on a CPU.
