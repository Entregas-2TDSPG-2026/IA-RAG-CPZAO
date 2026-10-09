"""Avaliação real de perguntas e fontes. Requer índice e GEMINI_API_KEY."""

from __future__ import annotations

from app.rag import RagService

CASES = [
    {
        "question": "O que é RAG e por que ele usa embeddings?",
        "status": "answered",
        "source_hint": "/aulas/genAI/lab4/",
    },
    {
        "question": "Como o KNN classifica uma nova amostra?",
        "status": "answered",
        "source_hint": "/aulas/IA/lab02/",
    },
    {
        "question": "Qual a diferença entre memória da conversa e base de conhecimento?",
        "status": "answered",
        "source_hint": "/aulas/genAI/lab4/",
    },
    {
        "question": "Qual é a capital do Canadá?",
        "status": "insufficient",
        "source_hint": None,
    },
    {
        "question": "Pode explicar melhor?",
        "status": "clarify",
        "source_hint": None,
    },
]


def main() -> None:
    service = RagService()
    failures: list[str] = []
    print(
        f"Base: {service.metadata['pages']} páginas, "
        f"{service.metadata['chunks']} trechos.\n"
    )
    for case in CASES:
        result = service.answer(case["question"], [])
        urls = [source["url"] for source in result["sources"]]
        print(f"Pergunta: {case['question']}")
        print(f"Status: {result['status']}")
        print(f"Resposta: {result['answer']}")
        print("Fontes:", *urls, sep="\n  ")
        print()
        if result["status"] != case["status"]:
            failures.append(f"Status incorreto: {case['question']}")
        if case["source_hint"] and not any(case["source_hint"] in url for url in urls):
            failures.append(f"Fonte esperada não encontrada: {case['question']}")
        if not case["source_hint"] and urls:
            failures.append(f"Fontes indevidas: {case['question']}")
    if failures:
        raise SystemExit("Avaliação falhou:\n- " + "\n- ".join(failures))
    print("Avaliação concluída: status e fontes esperados encontrados.")


if __name__ == "__main__":
    main()
