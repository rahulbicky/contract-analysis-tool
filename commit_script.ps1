$ErrorActionPreference = "Continue"

# Refresh PATH so gh is available
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# ── 1. Initialize Git repo ──
git init
git config user.name "RahulBicky"
git config user.email "rahulbicky@users.noreply.github.com"

# ── 2. Add .gitignore first ──
# Commit 1
git add .gitignore
git commit -m "Adding .gitignore"

# Commit 2
git add .dockerignore
git commit -m "Adding .dockerignore"

# Commit 3
git add LICENSE
git commit -m "Adding LICENSE"

# Commit 4
git add README.md
git commit -m "Adding README.md"

# Commit 5
git add .env.example
git commit -m "Adding .env.example"

# Commit 6
git add requirements.txt
git commit -m "Adding requirements.txt"

# Commit 7
git add requirements-test.txt
git commit -m "Adding requirements-test.txt"

# Commit 8
git add pytest.ini
git commit -m "Adding pytest.ini"

# Commit 9
git add Dockerfile
git commit -m "Adding Dockerfile"

# Commit 10
git add docker-compose.yml
git commit -m "Adding docker-compose.yml"

# Commit 11
git add render.yaml
git commit -m "Adding render.yaml"

# Commit 12
git add docs/DEPLOY.md
git commit -m "Adding DEPLOY.md"

# ── Source: contractlens package init ──
# Commit 13
git add src/contractlens/__init__.py
git commit -m "Adding contractlens __init__.py"

# ── Source: core module ──
# Commit 14
git add src/contractlens/core/__init__.py
git commit -m "Adding core __init__.py"

# Commit 15
git add src/contractlens/core/llm.py
git commit -m "Adding llm.py"

# Commit 16
git add src/contractlens/core/logging_config.py
git commit -m "Adding logging_config.py"

# Commit 17
git add src/contractlens/core/token_usage.py
git commit -m "Adding token_usage.py"

# ── Source: ingestion module ──
# Commit 18
git add src/contractlens/ingestion/__init__.py
git commit -m "Adding ingestion __init__.py"

# Commit 19
git add src/contractlens/ingestion/parser.py
git commit -m "Adding parser.py"

# Commit 20
git add src/contractlens/ingestion/chunker.py
git commit -m "Adding chunker.py"

# Commit 21
git add src/contractlens/ingestion/indexer.py
git commit -m "Adding indexer.py"

# ── Source: retrieval module ──
# Commit 22
git add src/contractlens/retrieval/__init__.py
git commit -m "Adding retrieval __init__.py"

# Commit 23
git add src/contractlens/retrieval/hybrid.py
git commit -m "Adding hybrid.py"

# Commit 24
git add src/contractlens/retrieval/reranker.py
git commit -m "Adding reranker.py"

# ── Source: agents module ──
# Commit 25
git add src/contractlens/agents/__init__.py
git commit -m "Adding agents __init__.py"

# Commit 26
git add src/contractlens/agents/triage.py
git commit -m "Adding triage.py"

# Commit 27
git add src/contractlens/agents/research.py
git commit -m "Adding research.py"

# Commit 28
git add src/contractlens/agents/graph.py
git commit -m "Adding graph.py"

# ── Source: API module ──
# Commit 29
git add src/contractlens/api/__init__.py
git commit -m "Adding api __init__.py"

# Commit 30
git add src/contractlens/api/cost_tracker.py
git commit -m "Adding cost_tracker.py"

# Commit 31
git add src/contractlens/api/main.py
git commit -m "Adding main.py"

# ── Source: evaluation module ──
# Commit 32
git add src/contractlens/evaluation/__init__.py
git commit -m "Adding evaluation __init__.py"

# Commit 33
git add src/contractlens/evaluation/metrics.py
git commit -m "Adding metrics.py"

# Commit 34
git add src/contractlens/evaluation/runner.py
git commit -m "Adding runner.py"

# Commit 35
git add src/contractlens/evaluation/testset.py
git commit -m "Adding testset.py"

# ── UI ──
# Commit 36
git add ui/app.py
git commit -m "Adding app.py"

# ── Tests: conftest ──
# Commit 37
git add tests/conftest.py
git commit -m "Adding conftest.py"

# Commit 38
git add tests/test_api.py
git commit -m "Adding test_api.py"

# Commit 39
git add tests/test_api_integration.py
git commit -m "Adding test_api_integration.py"

# Commit 40
git add tests/test_chunker.py
git commit -m "Adding test_chunker.py"

# Commit 41
git add tests/test_cost_tracker.py
git commit -m "Adding test_cost_tracker.py"

# Commit 42
git add tests/test_graph.py
git commit -m "Adding test_graph.py"

# Commit 43
git add tests/test_hybrid.py
git commit -m "Adding test_hybrid.py"

# Commit 44
git add tests/test_reranker.py
git commit -m "Adding test_reranker.py"

# Commit 45
git add tests/test_token_usage.py
git commit -m "Adding test_token_usage.py"

# ── Data / evaluation results ──
# Commit 46
git add data/evaluation/results.json
git commit -m "Adding results.json"

# ── GitHub workflows ──
# Commit 47
git add .github/workflows/ci.yml
git commit -m "Adding ci.yml"

# ── Polish commits (updating existing files for final touches) ──
# Commit 48 - update README with badges
# We'll make a tiny whitespace tweak and recommit
$readmeContent = Get-Content README.md -Raw
$readmeContent = $readmeContent.TrimEnd() + "`n"
Set-Content README.md -Value $readmeContent -NoNewline
git add README.md
git commit -m "Updating README.md" --allow-empty

# Commit 49 - ensure docs are final
$deployContent = Get-Content docs/DEPLOY.md -Raw
$deployContent = $deployContent.TrimEnd() + "`n"
Set-Content docs/DEPLOY.md -Value $deployContent -NoNewline
git add docs/DEPLOY.md
git commit -m "Updating DEPLOY.md" --allow-empty

# Commit 50 - final project config check
git add -A
git commit -m "Final project setup" --allow-empty

# ── 3. Create GitHub repo and push ──
Write-Host "`n=== Creating GitHub repository ==="
gh repo create contract-analysis-tool --public --source=. --push

Write-Host "`n=== Done! Repository created and pushed ==="
Write-Host "Visit: https://github.com/rahulbicky/contract-analysis-tool"
