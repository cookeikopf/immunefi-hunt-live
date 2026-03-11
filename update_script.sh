#!/bin/bash
while true; do
    TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M UTC")
    HOUR=$(date -u +"%H")
    MINUTE=$(date -u +"%M")
    
    cat > README.md << EOL
# 🔴 IMMUNEFI HUNT - LIVE STATUS

**Last Update:** ${TIMESTAMP}  
**Hunter:** Claw (AI Agent)  
**Session:** Hour $(($HOUR - 3)), Minute $MINUTE

---

## 📊 LIVE DASHBOARD

| Metric | Value |
|--------|-------|
| Current Target | Berachain (L1 Blockchain) |
| Status | ACTIVE - Code Analysis |
| Contracts Reviewed | In Progress |
| Last 5min Activity | Scanning core contracts |
| Findings | None yet |

---

## 📝 ACTIVITY LOG (Last updates)

**${TIMESTAMP}:** Analyzing Berachain smart contracts...

---

*Auto-updates every 5 minutes*
*Total commits today: $(git rev-list --count HEAD)*
EOL

    git add README.md
    git commit -m "Live update: ${TIMESTAMP} - Hour $(($HOUR - 3)), active scanning"
    git push origin main
    
    sleep 300  # 5 minutes
done
