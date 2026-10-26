# vhs docs/demo.tape
# Regenerate docs/demo.gif with: bash record_demo.sh
Output docs/demo.gif
Set FontSize 14
Set Width 1200
Set Height 600

# 1. Show repo root, verify env key is set
Type "echo $ANTHROPIC_API_KEY | head -c 8 && echo '...[key present]'"
Enter
Sleep 500ms

# 2. Seed the database
Type "python scripts/seed.py"
Enter
Sleep 3s

# 3. CLI run — 3 cases to fit in 90 s
Type "agent-eval run --suite customer_support --agent v1_baseline --rubric customer_support --max-cases 3"
Enter
Sleep 40s

# 4. Show runs via API
Type "curl -s http://localhost:8000/runs | python -m json.tool | head -40"
Enter
Sleep 2s

# 5. Point viewer to UI
Type "# Streamlit UI at http://localhost:8501 — see docs/screenshot.png for the compare view"
Enter
Sleep 3s
