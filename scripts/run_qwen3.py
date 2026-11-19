import os

from llama_cpp import Llama


def main() -> None:
    model_path = os.environ.get(
        "QWEN3_MODEL_PATH",
        "models/Qwen3-1.7B-Q8_0.gguf",
    )
    prompt = os.environ.get(
        "QWEN3_PROMPT",
        "Viết một hàm Python kiểm tra số nguyên tố.",
    )

    llm = Llama(
        model_path=model_path,
        n_ctx=2048,
        n_threads=int(os.environ.get("OMP_NUM_THREADS", "2")),
        verbose=False,
    )
    response = llm.create_chat_completion(
        messages=[
            {
                "role": "system",
                "content": "Bạn là trợ lý lập trình Python ngắn gọn.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        temperature=0.6,
        top_p=0.95,
    )

    print(response["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
