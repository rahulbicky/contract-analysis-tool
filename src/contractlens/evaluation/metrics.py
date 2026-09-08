# src/evaluation/metrics.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from contractlens.core.llm import get_chat_model

load_dotenv()


def exact_match(prediction: str, ground_truth: str) -> float:
    pred_lower = prediction.lower()
    truth_lower = ground_truth.lower()

    # Normalize numbers — "sixty (60)" and "60" should match
    import re
    pred_lower = re.sub(r'\((\d+)\)', r'\1', pred_lower)
    truth_lower = re.sub(r'\((\d+)\)', r'\1', truth_lower)

    # Extract key phrases — split on comma AND period
    key_phrases = [
        phrase.strip()
        for phrase in re.split(r'[,.]', truth_lower)
        if len(phrase.strip()) > 8
    ]

    if not key_phrases:
        return 1.0 if truth_lower in pred_lower else 0.0

    matches = sum(
        1 for phrase in key_phrases
        if any(word in pred_lower for word in phrase.split() if len(word) > 4)
    )
    return round(matches / len(key_phrases), 2)


def faithfulness_score(
    answer: str,
    context: str,
    llm=None
) -> float:
    """
    LLM-as-judge: Is the answer faithful to the retrieved context?
    Returns 0.0 to 1.0
    """
    if llm is None:
        llm = get_chat_model(temperature=0)

    prompt = ChatPromptTemplate.from_template("""
You are evaluating if an answer is faithful to the provided context.
Faithful means: every claim in the answer is supported by the context.
No hallucinations or made-up information.

Context:
{context}

Answer:
{answer}

Rate faithfulness from 0 to 10:
- 10: Every claim is directly supported by context
- 7-9: Most claims supported, minor gaps
- 4-6: Some claims supported, some not
- 0-3: Many claims not in context or contradicted

Respond with ONLY a number 0-10. Nothing else.""")

    messages = prompt.format_messages(
        context=context[:3000],
        answer=answer
    )
    response = llm.invoke(messages)

    try:
        score = float(response.content.strip()) / 10.0
        return round(score, 2)
    except:
        return 0.0


def answer_relevancy_score(
    question: str,
    answer: str,
    llm=None
) -> float:
    """
    LLM-as-judge: Does the answer actually address the question?
    Returns 0.0 to 1.0
    """
    if llm is None:
        llm = get_chat_model(temperature=0)

    prompt = ChatPromptTemplate.from_template("""
Does this answer actually address the question asked?

Question: {question}
Answer: {answer}

Rate relevancy from 0 to 10:
- 10: Directly and completely answers the question
- 7-9: Mostly answers with minor gaps
- 4-6: Partially answers
- 0-3: Does not answer or goes off topic

Respond with ONLY a number 0-10. Nothing else.""")

    messages = prompt.format_messages(
        question=question,
        answer=answer
    )
    response = llm.invoke(messages)

    try:
        score = float(response.content.strip()) / 10.0
        return round(score, 2)
    except:
        return 0.0


def context_precision_score(
    question: str,
    retrieved_chunks: list[str],
    ground_truth: str,
    llm=None
) -> float:
    """
    Are the retrieved chunks actually relevant to answer the question?
    Returns 0.0 to 1.0
    """
    if llm is None:
        llm = get_chat_model(temperature=0)

    if not retrieved_chunks:
        return 0.0

    relevant_count = 0
    for chunk in retrieved_chunks[:5]:
        prompt = ChatPromptTemplate.from_template("""
Is this chunk useful for answering the question?

Question: {question}
Chunk: {chunk}

Respond with ONLY yes or no.""")

        messages = prompt.format_messages(
            question=question,
            chunk=chunk[:500]
        )
        response = llm.invoke(messages)
        if "yes" in response.content.lower():
            relevant_count += 1

    return round(relevant_count / len(retrieved_chunks[:5]), 2)


def compute_all_metrics(
    question: str,
    answer: str,
    context: str,
    ground_truth: str,
    retrieved_chunks: list[str],
    llm=None
) -> dict:
    """
    Compute all metrics for one test case.
    """
    if llm is None:
        llm = get_chat_model(temperature=0)

    return {
        "exact_match": exact_match(answer, ground_truth),
        "faithfulness": faithfulness_score(answer, context, llm),
        "answer_relevancy": answer_relevancy_score(question, answer, llm),
        "context_precision": context_precision_score(
            question, retrieved_chunks, ground_truth, llm
        )
    }