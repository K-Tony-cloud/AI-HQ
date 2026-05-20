# 🧠 AI-HQ
KTony Team Operating System

---

# Overview

AI-HQ คือระบบจัดการทีม AI ของ KTony Team

เป้าหมาย:
- ทำงานร่วมกันแบบทีม
- ลด token usage
- ทำโปรเจกต์ต่อเนื่องได้
- แยกหน้าที่ AI ชัดเจน
- scale โปรเจกต์ในอนาคต

---

# Core Rules

- Roxi คือ Team Lead
- ทุก AI มี role ชัดเจน
- ห้ามทำงานข้าม role
- ทุกโปรเจกต์ต้องมี summary
- ใช้เฉพาะ context ที่จำเป็น
- ห้าม paste full project ถ้าไม่จำเป็น

---

# Team Members

| Name | Role |
|---|---|
| Roxi | CEO / Project Manager |
| Kiki | Content Creator |
| Vixi | Video / Visual |
| Nova | Developer |
| Cipher | QA / Critic |
| Luna | Analyst |
| Speedy | Growth / Marketing |

---

# Workflow

1. Roxi รับงาน
2. แจก task
3. ทีม execute
4. Cipher review
5. Roxi summarize

---

# Folder Structure

```txt
AI-HQ/
│
├── README.md
├── PERSONAS/                        # AI team member role definitions
│   ├── Roxi.md
│   ├── Nova.md
│   ├── Kiki.md
│   ├── Vixi.md
│   ├── Cipher.md
│   ├── Luna.md
│   └── Speedy.md
├── PROJECTS/                        # Active projects (see PROJECTS/README.md)
│   ├── README.md                    # Project index
│   ├── line-reminder/               # LINE reminder bot (Railway) — own git repo
│   ├── SheetAppScriptRW01/          # Police station system backend — own git repo
│   └── rw-inv-redirect/             # Police station system frontend — own git repo
├── CONTEXT/                         # Shared context files
├── PROMPTS/                         # Reusable prompt templates
├── SYSTEM/                          # System-level configuration
└── ARCHIVE/                         # Inactive / retired work
```

---

# Active Projects

| Project | Stack | Deployment |
|---|---|---|
| line-reminder | Python / FastAPI / LINE SDK | Railway |
| Police Station Visitor System (RW01) | Google Apps Script / Google Sheets | GAS + GitHub Pages |

---

# Token Rules

DO:
- use summary
- use latest task
- modular context
- use markdown

DON'T:
- repeat context
- paste full code
- explain everything repeatedly

---

# Philosophy

Build scalable AI workflow system for:
- content
- development
- automation
- monetization