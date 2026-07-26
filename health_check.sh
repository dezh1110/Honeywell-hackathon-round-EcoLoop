#!/bin/bash
echo "════════════════════════════════════════"
echo "1. CONTAINER STATUS"
echo "════════════════════════════════════════"
docker compose ps

echo ""
echo "════════════════════════════════════════"
echo "2. RECENT ERRORS (last 5 minutes)"
echo "════════════════════════════════════════"
ERRORS=$(docker compose logs backend --since 5m 2>&1 | grep -iE "traceback|error|exception" | grep -v "INFO" | tail -10)
if [ -z "$ERRORS" ]; then
  echo "✅ No errors found"
else
  echo "⚠️  Found errors:"
  echo "$ERRORS"
fi

echo ""
echo "════════════════════════════════════════"
echo "3. POLLERS RUNNING?"
echo "════════════════════════════════════════"
docker compose logs backend 2>&1 | grep "poller" | tail -3

echo ""
echo "════════════════════════════════════════"
echo "4. RECENT TELEMETRY (backend actually producing data?)"
echo "════════════════════════════════════════"
docker compose logs backend --since 5m 2>&1 | grep "baseline=" | tail -5

echo ""
echo "════════════════════════════════════════"
echo "5. LLM REASONING SUCCEEDING?"
echo "════════════════════════════════════════"
docker compose logs backend --since 5m 2>&1 | grep "chat/completions" | tail -5

echo ""
echo "════════════════════════════════════════"
echo "6. SUPABASE - MOST RECENT ROW IN EACH TABLE"
echo "════════════════════════════════════════"
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi
for TABLE in building_telemetry building_logs nlp_queries whatif_requests; do
  echo "--- $TABLE ---"
  curl -s "${VITE_SUPABASE_URL}/rest/v1/${TABLE}?select=created_at&order=created_at.desc&limit=1" \
    -H "apikey: ${VITE_SUPABASE_ANON_KEY}" \
    -H "Authorization: Bearer ${VITE_SUPABASE_ANON_KEY}"
  echo ""
done

echo ""
echo "════════════════════════════════════════"
echo "7. OLLAMA MODEL CHECK"
echo "════════════════════════════════════════"
docker compose exec -T ollama ollama list
