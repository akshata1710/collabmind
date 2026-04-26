import asyncio
from app.services.evaluator import run_all_evals

if __name__ == "__main__":
    asyncio.run(run_all_evals())