# 🛰️ Sentinel-SDLC: Multi-Agent Security Compliance

Sentinel-SDLC is a modern, AI-driven security compliance engine designed to gate Pull Requests with state-of-the-art semantic reasoning. It moves beyond legacy regex-based scanning by utilizing a Distributed Multi-Agent Graph to analyze code changes for deep security risks, PII exposure, and hardcoded secrets.

---

## 🏗️ Architecture: Multi-Agent Sentinel (RAV)

Sentinel operates as a **Retrieval-Augmented Validation (RAV)** system. When a webhook is received, it triggers a multi-stage LangGraph pipeline:

```mermaid
graph TB
    subgraph "Google Cloud Platform (us-central1)"
        subgraph "Cloud Run: Sentinel Orchestrator"
            C[Sentinel Orchestrator FastAPI] --> OP[OpenTelemetry]
            C --> D[LangGraph State Machine]
            C -- /api/copilot --> CP[Copilot Agent]
            
            subgraph "Agents"
                D --> E[Scout Agent: Fetch Context]
                D --> F[Analyst Agent: Ticket Alignment]
                D --> G[Validator Agent: Security Check]
                D --> R[Reporter Agent: Final Verdict]
            end
        end

        subgraph "Cloud Run: Java Evaluator"
            H[Java Evaluator] --> I[SecurityAIService: LangChain4j]
            I --> J[Deterministic Shield: Regex/PII]
        end

        subgraph "MCP Servers (Subprocesses)"
            N[Jira MCP (stdio)]
            S[Standards MCP (stdio)]
        end

        subgraph "Firestore Serverless"
            FS[(Verdict History)]
        end

        subgraph "Secret Manager"
            M[API Keys & GitHub Secrets]
        end

        M -- Secret Mount --> C
        M -- Secret Mount --> H
        FS -- Reads Context --> CP
        R -- Persists Verdict --> FS
    end

    A[GitHub Repository] -- Webhook --> C
    A -- Copilot Chat --> C
    E -- Fetch Raw Diff (HTTP) --> A
    
    F -- Requirements Context (stdio) --> N
    G -- Enterprise Rules (stdio) --> S
    
    G -- Internal Call: OIDC/JWT --> H
    R -- Decision --> K[GitHub Check Runs]
    
    OP -- Export Traces --> CT[Google Cloud Trace]

    subgraph "External Foundation Models"
        F -- Alignment Scan (API) --> L[Google Gemini]
        G -- Security Scan (API) --> L
        I -- Deep Scan (API) --> L
        CP -- Chat Reasoning --> L
    end

    subgraph "External Cloud Services"
        N -- REST API (OAuth) --> Atlassian[Jira Cloud]
    end
```

### 🧠 Core Components

- **`scout-agent`**: Fetches the PR diff and identifies the relevant enterprise standards.
- **`analyst-agent`**: Performs deep semantic analysis and ticket alignment using **LangChain-Python**.
- **`validator-agent`**: Enforces enterprise rules utilizing MCP knowledge bases.
- **`reporter-agent`**: Formulates the definitive GO/NO-GO decision based on prior agent signals and persists the verdict to **Firestore**.
- **`Java Evaluator` & `SecurityAIService`**: The deterministic/AI shield using **LangChain4j** for secrets and PII detection. Secured via **Spring Security (OIDC/JWT)**.
- **`Copilot Agent`**: Chat interface allowing developers to diagnose blocked PRs directly via the GitHub Copilot Extension, referencing the **Firestore Verdict History**.
- **`MCP Suite`**: Internal context injection using Model Context Protocol endpoints (Jira, Standards) hosted as `stdio` subprocesses alongside the orchestrator.
- **`OpenTelemetry`**: Emits robust execution traces directly to Google Cloud Trace for internal pipeline auditing and observability.

---

## 🛠️ Technology Stack

- **Orchestrator (Python)**: [FastAPI](https://fastapi.tiangolo.com/), [LangGraph](https://python.langchain.com/docs/langgraph), [PyGithub](https://github.com/PyGithub/PyGithub).
- **Evaluator (Java)**: [Spring Boot](https://spring.io/projects/spring-boot), [LangChain4j](https://github.com/langchain4j/langchain4j).
- **AI Engine**: [Google Gemini Flash (Latest)](https://deepmind.google/technologies/gemini/).
- **Infrastructure**: [Google Cloud Run](https://cloud.google.com/run), [GitHub Actions](https://github.com/features/actions).

---

## 🚀 Setup & Deployment

### 1. Environment Variables
Ensure the following variables are configured in **GCP Secret Manager**:

| Variable | Description |
| :--- | :--- |
| `GITHUB_APP_ID` | The ID of your GitHub App. |
| `GITHUB_PRIVATE_KEY` | The RSA private key for your GitHub App. |
| `GITHUB_WEBHOOK_SECRET` | The secret used to verify webhook signatures. |
| `GOOGLE_API_KEY` | Your Google AI (Gemini) API Key. |
| `EVALUATOR_URL` | The URL of the internal Java Evaluator service. |
| `SENTINEL_ADMIN_LOGINS` | Comma-separated list of GitHub logins with ADMIN privileges. |
| `SENTINEL_HISTORY_BACKEND` | E.g., `firestore`, controls how verdict history is stored. |
| `SENTINEL_FIRESTORE_DATABASE` | Targeted Firestore Database Name (e.g. `sentinel`). |

### 2. Local Development
```bash
# Orchestrator
cd orchestrator
pip install -r requirements.txt
python main.py

# Evaluator
cd evaluator
./gradlew bootRun
```

### 3. Deployment
The services are automatically deployed to Google Cloud Run via the `.github/workflows/deploy.yml` pipeline.

---

## 🛡️ Usage: Sentinel PR Gating

Sentinel is enforced via **GitHub Branch Protection Rulesets**. 
1. Open a Pull Request.
2. The **Sentinel Compliance Check** will trigger automatically.
3. If the AI detects a violation (e.g., hardcoded credentials or unauthenticated internal calls), the check will fail and block the merge.
4. Review the detailed agent trace in the PR comments to remediate the findings.

---

## 🔒 Security & RBAC

Sentinel-SDLC implements a multi-layered security model following the principle of least privilege:

- **Identity Propagation**: The Orchestrator extracts the GitHub identity of the PR author or Copilot user and maps it to specific roles (e.g., `ADMIN`, `DEVELOPER`).
- **Service-to-Service Authorization**: Internal communication between the Orchestrator and Evaluator is secured via **GCP IAM (roles/run.invoker)** and verified using **OIDC ID Tokens / Spring Security**. Special Service Accounts (`sentinel-orchestrator` and `sentinel-evaluator`) enforce distinct boundaries.
- **Governance Proxy**: The custom MCP servers act as a security bridge, redacting sensitive Jira/Standards data before it reaches external LLM endpoints.
- **Audit Logging & State Tracking**: Every agent execution is traced and logged with the requester's identity in Google Cloud Trace, and permanent verdicts are stored via **Firestore**.

---

> [!TIP]
> **Performance**: The system uses **Gemini Flash** for ultra-low latency semantic scans, typically completing a full PR analysis in under 10 seconds.

*Powered by Sentinel-SDLC • Built for Enterprise Governance*
