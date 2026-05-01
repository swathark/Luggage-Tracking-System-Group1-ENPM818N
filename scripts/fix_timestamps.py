import sqlite3

conn = sqlite3.connect('local_luggage.db')
c = conn.cursor()

# Find rows where sla_due_at has ISO T separator
c.execute("SELECT id, sla_due_at FROM support_tickets WHERE sla_due_at LIKE '%T%'")
rows = c.fetchall()
print(f"Found {len(rows)} rows with T-separator timestamps")

for row in rows:
    tid, sla = row
    fixed = sla.replace('T', ' ')
    # Also strip microseconds if present
    if '.' in fixed:
        fixed = fixed.split('.')[0]
    c.execute("UPDATE support_tickets SET sla_due_at = ? WHERE id = ?", (fixed, tid))
    print(f"  Fixed ticket #{tid}: {sla} -> {fixed}")

conn.commit()
print("Done!")
conn.close()
