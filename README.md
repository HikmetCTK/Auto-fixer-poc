# Auto-fixer: Autonomous Multi-Agent Bug Fixer (Proof of Concept)

Auto-fixer is an experimental Proof of Concept (PoC) demonstrating how a multi-agent AI system can autonomously detect, analyze, fix, and verify code bugs. 

The goal of this project is to explore the end-to-end workflow of triggering an AI system with an error trace and letting it attempt to find the root cause, write a patch, test it in an isolated sandbox, and finally branch the code for human review.

---

## 💡 Concept & Features

This PoC showcases the following experimental workflow:
- **Error Analysis:** Parses stack traces and error logs to identify the problem.
- **Agent Collaboration:** Uses specialized AI agents with different roles (Analyzer, Fixer, Researcher, Orchestrator) to divide the debugging tasks.
- **Docker Sandbox Execution:** Attempts to validate the AI-generated code by running the project's test suite inside an isolated Docker container.
- **Git Integration:** Instead of modifying the main branch, if a fix passes the sandbox test, the agent creates a new git branch, commits the changes, and pushes them for review (simulating a Pull Request workflow).
- **Visualization:** A simple Next.js frontend to observe the agents' internal thoughts and tool executions in real-time.

---

## 🤖 Agent Roles

The multi-agent system is divided into several specialized roles:

1. **`ErrorAnalyzerAgent`**: Receives the initial error, searches the codebase to find the failing code, and identifies the root cause.
2. **`FixSuggesterAgent`**: Takes the analysis and proposes a logical code fix.
3. **`AutoFixerAgent`**: Applies the suggested fix to the files, runs the test suite in a Docker container, and if successful, pushes the changes to a new Git branch.
4. **`ResearchAgent`**: Falls back to web search if external documentation or context is needed.
5. **`Orchestrator`**: Manages the flow between the different agents.
6. **`Reporter`**: Outputs a summary of the actions taken.

---

## 🛠️ Tech Stack

- **Backend / Agents:** Python, FastAPI, Pydantic, LLM Integration
- **Dependency Management:** `uv`
- **Frontend:** Next.js (built with TypeScript and TailwindCSS)
- **Execution Environment:** Docker (for sandbox testing)

---

## 🚀 Running the PoC

### Prerequisites
- [Python 3.10+](https://www.python.org/)
- [`uv`](https://docs.astral.sh/uv/) for Python dependency management
- Docker Desktop / Daemon (Must be running for sandbox testing)
- Git

### 1. Setup Environment
Clone the repository and set up your environment variables:
```bash
git clone https://github.com/yourusername/end-to-end-multi-agent.git
cd end-to-end-multi-agent

cp .env.example .env
```
*Note: Make sure to add your necessary API keys (e.g., `OPENAI_API_KEY`) to the `.env` file.*

### 2. Run the Backend API
The backend is managed by `uv`:
```bash
# Install dependencies and sync the environment
uv sync

# Run the FastAPI server
uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Run the Frontend UI
The web interface allows you to monitor the agents as they work.
```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## ⚠️ Limitations & Notes

- **Proof of Concept:** This project is for experimental and educational purposes. It is **not** intended for production use.
- **Accuracy:** The system's ability to fix bugs relies heavily on the underlying LLM's capabilities and may produce incorrect or hallucinated fixes.(Local models were not good to produce structured response and tool calling)
