# src/evaluation/runner.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pandas as pd
from langchain_core.prompts import ChatPromptTemplate
from contractlens.core.llm import get_chat_model
from contractlens.retrieval.reranker import retrieve_and_rerank
from contractlens.evaluation.testset import TEST_CASES
from contractlens.evaluation.metrics import compute_all_metrics
from dotenv import load_dotenv
import logging
from contractlens.core.logging_config import configure_logging

logger = logging.getLogger(__name__)

load_dotenv()


def answer_question(question: str, llm, filename_filter: str = None) -> tuple[str, str, list[str]]:
    docs = retrieve_and_rerank(question, k_retrieve=20, k_final=5, filename_filter=filename_filter)

    context = "\n\n".join([doc.page_content for doc in docs])
    retrieved_chunks = [doc.page_content for doc in docs]

    prompt = ChatPromptTemplate.from_template("""
You are a contract analysis assistant.
Answer the question based only on the provided context.
If the answer is not in the context say "Not found in document."
Be specific and quote relevant text when possible.

Context:
{context}

Question: {question}

Answer:""")

    messages = prompt.format_messages(context=context, question=question)
    response = llm.invoke(messages)
    return response.content, context, retrieved_chunks


def run_evaluation(
    test_cases: list[dict] = None,
    output_path: str = "./data/evaluation/results.json"
) -> pd.DataFrame:
    """
    Run full evaluation on all test cases.
    Saves results to JSON and returns DataFrame.
    """
    if test_cases is None:
        test_cases = TEST_CASES

    os.makedirs("./data/evaluation", exist_ok=True)

    llm = get_chat_model(temperature=0)
    results = []

    logger.info(f"\nRunning evaluation on {len(test_cases)} test cases...\n")

    for i, tc in enumerate(test_cases, 1):
        logger.info(f"[{i}/{len(test_cases)}] {tc['id']}: {tc['question'][:60]}...")

        try:
            # Filter retrieval to the test case's source document, unless it's
            # explicitly a cross-document question ("both") -- keeps unrelated
            # contracts' chunks out of the candidate set (see context_precision).
            document = tc.get("document")
            filename_filter = document if document and document != "both" else None

            # Get answer from system
            answer, context, chunks = answer_question(tc["question"], llm, filename_filter=filename_filter)

            # Compute metrics
            metrics = compute_all_metrics(
                question=tc["question"],
                answer=answer,
                context=context,
                ground_truth=tc["ground_truth"],
                retrieved_chunks=chunks,
                llm=llm
            )

            result = {
                "id": tc["id"],
                "category": tc["category"],
                "difficulty": tc["difficulty"],
                "question": tc["question"],
                "ground_truth": tc["ground_truth"],
                "answer": answer,
                **metrics
            }

            results.append(result)

            logger.info(f"  ✅ EM: {metrics['exact_match']:.2f} | "
                  f"Faith: {metrics['faithfulness']:.2f} | "
                  f"Rel: {metrics['answer_relevancy']:.2f} | "
                  f"Prec: {metrics['context_precision']:.2f}")

        except Exception as e:
            logger.error(f"  ❌ Failed: {e}")
            results.append({
                "id": tc["id"],
                "category": tc["category"],
                "difficulty": tc["difficulty"],
                "question": tc["question"],
                "ground_truth": tc["ground_truth"],
                "answer": "ERROR",
                "exact_match": 0.0,
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "context_precision": 0.0
            })

    # Save results
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    df = pd.DataFrame(results)

    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("EVALUATION SUMMARY")
    logger.info(f"{'='*60}")

    metrics = ["exact_match", "faithfulness", "answer_relevancy", "context_precision"]

    logger.info(f"\nOverall averages:")
    for m in metrics:
        logger.info(f"  {m:25s}: {df[m].mean():.3f}")

    logger.info(f"\nBy difficulty:")
    logger.info(df.groupby("difficulty")[metrics].mean().round(3).to_string())

    logger.info(f"\nBy category:")
    logger.info(df.groupby("category")[metrics].mean().round(3).to_string())

    logger.info(f"\n💾 Results saved to {output_path}")

    return df


if __name__ == "__main__":
    configure_logging()
    df = run_evaluation()