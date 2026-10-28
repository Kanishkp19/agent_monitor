"""Employee chair positions for infra/scripts/extract_furniture.py.

Mirrors EmployeeCatalog RAW_EMPLOYEES (id, name, role, team, agent, room,
global tile, facing). Kept as plain data so the extractor stays stdlib-only
and independent of the TS bundle. Origins per the tower-block layout in
WorldRenderer ROOMS (local anchors + origin).
"""

EMPLOYEES: list[tuple[str, str, str, str, str, str, tuple[float, float], str]] = [
    ("emp_001", "Vikram Nair", "CEO", "exec", "internal", "ceo_office", (25.0, 16.0), "e"),
    ("emp_002", "Sara Iyer", "Senior Manager", "platform", "claude_code", "managers", (25.66, 6.0), "n"),
    ("emp_003", "Ben Mathew", "Manager", "payments", "claude_code", "managers", (26.66, 3.0), "e"),
    ("emp_004", "Sarah Khan", "Senior Eng.", "payments", "claude_code", "dev_floor", (2.47, 2.84), "e"),
    ("emp_005", "Arjun Menon", "Senior Eng.", "platform", "codex", "dev_floor", (6.47, 2.84), "e"),
    ("emp_006", "Neha Gupta", "Senior Eng.", "data", "claude_code", "dev_floor", (10.47, 2.84), "e"),
    ("emp_007", "Priya Sharma", "Engineer", "payments", "codex", "dev_floor", (14.47, 2.84), "e"),
    ("emp_008", "Aman Verma", "Engineer", "payments", "codex", "dev_floor", (2.47, 7.84), "e"),
    ("emp_009", "Rohit Das", "Engineer", "platform", "claude_code", "dev_floor", (6.47, 7.84), "e"),
    ("emp_012", "Ananya Roy", "Engineer", "data", "codex", "dev_floor", (10.47, 7.84), "e"),
    ("emp_013", "Rahul Sharma", "Engineering Intern", "payments", "codex", "dev_floor", (14.47, 7.84), "e"),
    ("emp_014", "Ishaan Bose", "Engineering Intern", "payments", "codex", "dev_floor", (2.47, 12.84), "e"),
    ("emp_017", "Nikhil Rao", "Engineer", "platform", "internal", "dev_floor", (6.47, 12.84), "e"),
    ("emp_018", "Zoya Ahmed", "Engineering Intern", "platform", "claude_code", "dev_floor", (10.47, 12.84), "e"),
    ("emp_020", "Lakshmi Iyer", "Engineer", "data", "claude_code", "dev_floor", (14.47, 12.84), "e"),
    ("emp_019", "Mark Dsouza", "DevOps", "platform", "internal", "devops", (26.0, 24.0), "n"),
    ("emp_010", "Meera Pillai", "Engineer", "frontend", "claude_code", "meeting_room", (4.02, 20.0), "s"),
    ("emp_011", "Kabir Shah", "Engineer", "frontend", "mcp", "meeting_room", (6.42, 20.0), "s"),
    ("emp_015", "Tara Nair", "Engineering Intern", "frontend", "claude_code", "meeting_room", (4.02, 28.0), "n"),
    ("emp_016", "Dev Malhotra", "Engineering Intern", "data", "codex", "meeting_room", (6.42, 28.0), "n"),
]
