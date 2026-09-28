"""Explicit model download/inference smoke check; does not access MongoDB."""
import asyncio
import json
from .sentiment import classifier


async def main():
    texts = ["This is an excellent initiative.", "This plan is terrible and disappointing.",
             "The meeting starts at ten tomorrow.", "यह बहुत अच्छा काम है।", "Yeh kaam bahut achha hai."]
    engine = classifier()
    results = await engine.classify(texts)
    print(json.dumps({'model': engine.provenance, 'results': [r.model_dump() for r in results]}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
