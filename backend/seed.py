from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from .utils import clone_json, format_compact, format_number, month_sort_stamp, month_year_label


CATEGORY_LIBRARY: dict[str, dict[str, Any]] = {
    "ai": {
        "label": "AI Engineering",
        "badgeClass": "badge-violet",
        "requirements": [
            "Basic Python or no-code curiosity",
            "A laptop with internet access",
            "Willingness to test ideas in public",
        ],
        "learn": [
            "Build prompt systems that solve real problems",
            "Create tool-calling assistants and agents",
            "Connect automations to business workflows",
            "Ship a portfolio project clients can understand",
            "Package and price AI services with confidence",
        ],
        "resources": [
            "Prompt system worksheet",
            "Function calling checklist",
            "Starter implementation outline",
        ],
        "qa": [
            {
                "question": "How much coding do I need?",
                "answer": "You can begin with guided examples and grow into heavier implementation as the projects become more advanced.",
            },
            {
                "question": "Can I use this for freelancing?",
                "answer": "Yes. The lessons are organized around offer creation, delivery quality, and repeatable client outcomes.",
            },
        ],
        "modules": [
            {
                "title": "Foundations and setup",
                "duration": "1h 20m",
                "lessons": [
                    {"title": "What makes an AI workflow useful?", "duration": "12:30", "type": "video", "free": True, "done": True},
                    {"title": "Project setup and environment basics", "duration": "18:45", "type": "video", "free": True, "done": True},
                    {"title": "Your first structured prompt flow", "duration": "21:10", "type": "video", "done": True},
                    {"title": "Readiness quiz", "duration": "10 min", "type": "quiz"},
                ],
            },
            {
                "title": "Prompt systems and structured outputs",
                "duration": "2h 05m",
                "lessons": [
                    {"title": "Prompt architecture for production tasks", "duration": "24:15", "type": "video", "done": True},
                    {"title": "Schemas, validation, and guardrails", "duration": "26:40", "type": "video"},
                    {"title": "Output review checklist", "duration": "PDF", "type": "pdf"},
                ],
            },
            {
                "title": "Tool use and automation",
                "duration": "2h 40m",
                "lessons": [
                    {"title": "Designing tool contracts", "duration": "28:40", "type": "video"},
                    {"title": "Handling retries and failures", "duration": "22:10", "type": "video"},
                    {"title": "Shipping an agent workflow", "duration": "31:00", "type": "video"},
                ],
            },
            {
                "title": "Deployment and monetization",
                "duration": "1h 45m",
                "lessons": [
                    {"title": "From demo to client-ready delivery", "duration": "19:35", "type": "video"},
                    {"title": "Simple hosting and observability", "duration": "24:20", "type": "video"},
                    {"title": "Offer design and pricing", "duration": "17:45", "type": "video"},
                ],
            },
        ],
    },
    "forex": {
        "label": "Forex Trading",
        "badgeClass": "badge-gold",
        "requirements": [
            "Basic market vocabulary helps but is not required",
            "A journal or note-taking habit",
            "Patience to practice risk management rules",
        ],
        "learn": [
            "Read higher-timeframe structure with confidence",
            "Build repeatable entry and exit routines",
            "Protect capital with practical risk rules",
            "Create a trading journal you will actually use",
            "Avoid emotional overtrading during live sessions",
        ],
        "resources": [
            "Risk calculator template",
            "Trade journal layout",
            "Session checklist",
        ],
        "qa": [
            {
                "question": "Is this for beginners?",
                "answer": "Yes. The roadmap starts with market structure, then layers in execution, review, and discipline.",
            },
            {
                "question": "Do you cover risk management?",
                "answer": "It is built into every module, not treated as an afterthought.",
            },
        ],
        "modules": [
            {
                "title": "Market structure and context",
                "duration": "1h 30m",
                "lessons": [
                    {"title": "Reading bullish and bearish structure", "duration": "15:20", "type": "video", "free": True, "done": True},
                    {"title": "Key highs, lows, and liquidity zones", "duration": "18:10", "type": "video", "done": True},
                    {"title": "Daily bias framework", "duration": "20:40", "type": "video"},
                ],
            },
            {
                "title": "Entries and confirmations",
                "duration": "2h 00m",
                "lessons": [
                    {"title": "Momentum and displacement", "duration": "21:15", "type": "video"},
                    {"title": "Retests, pullbacks, and invalidation", "duration": "24:45", "type": "video"},
                    {"title": "Execution checklist", "duration": "PDF", "type": "pdf"},
                ],
            },
            {
                "title": "Risk and trade management",
                "duration": "1h 50m",
                "lessons": [
                    {"title": "Position sizing without guesswork", "duration": "16:40", "type": "video"},
                    {"title": "Managing partials and runners", "duration": "18:25", "type": "video"},
                    {"title": "Risk quiz", "duration": "8 min", "type": "quiz"},
                ],
            },
            {
                "title": "Psychology and review",
                "duration": "1h 10m",
                "lessons": [
                    {"title": "Building a post-trade review loop", "duration": "14:30", "type": "video"},
                    {"title": "Controlling tilt and revenge trading", "duration": "12:50", "type": "video"},
                ],
            },
        ],
    },
    "video": {
        "label": "Video Editing",
        "badgeClass": "badge-gold",
        "requirements": [
            "A computer that can edit HD video",
            "Willingness to practice with raw footage",
            "Basic familiarity with folders and exports",
        ],
        "learn": [
            "Edit fast without losing structure",
            "Build clean timelines and motion sequences",
            "Improve pacing, sound, and retention",
            "Create reels, long-form lessons, and client cuts",
            "Export correctly for every platform",
        ],
        "resources": [
            "Editing workflow board",
            "Shortcut pack",
            "Export preset guide",
        ],
        "qa": [
            {
                "question": "Is this software specific?",
                "answer": "The principles transfer across major editors, while the workflows stay practical for the tools used in class.",
            },
            {
                "question": "Will I build portfolio pieces?",
                "answer": "Yes. The projects are designed to produce deliverables you can show to clients immediately.",
            },
        ],
        "modules": [
            {
                "title": "Workflow and timeline setup",
                "duration": "1h 05m",
                "lessons": [
                    {"title": "Media organization that scales", "duration": "10:20", "type": "video", "free": True, "done": True},
                    {"title": "Fast rough cuts and review passes", "duration": "16:45", "type": "video", "done": True},
                    {"title": "Project setup file", "duration": "PDF", "type": "pdf"},
                ],
            },
            {
                "title": "Story, pacing, and retention",
                "duration": "1h 55m",
                "lessons": [
                    {"title": "Hooking viewers in the first seconds", "duration": "19:40", "type": "video"},
                    {"title": "Cutting dead space and boosting rhythm", "duration": "22:30", "type": "video"},
                    {"title": "Sound and music layering", "duration": "17:10", "type": "video"},
                ],
            },
            {
                "title": "Motion and polish",
                "duration": "2h 10m",
                "lessons": [
                    {"title": "Transitions that feel intentional", "duration": "18:05", "type": "video"},
                    {"title": "Captions, callouts, and graphics", "duration": "25:00", "type": "video"},
                    {"title": "Color cleanup basics", "duration": "20:10", "type": "video"},
                ],
            },
            {
                "title": "Delivery and client handoff",
                "duration": "58m",
                "lessons": [
                    {"title": "Export settings by platform", "duration": "12:35", "type": "video"},
                    {"title": "Client revisions and versioning", "duration": "14:15", "type": "video"},
                ],
            },
        ],
    },
    "ads": {
        "label": "Facebook Ads",
        "badgeClass": "badge-gold",
        "requirements": [
            "A product, service, or practice offer to think through",
            "A willingness to test creatives and messaging",
            "Basic spreadsheet comfort for reporting",
        ],
        "learn": [
            "Build campaigns around real buying intent",
            "Align creatives with audience stages",
            "Read metrics without getting distracted",
            "Improve landing pages and follow-up flows",
            "Create simple reporting for clients or teams",
        ],
        "resources": [
            "Creative angle bank",
            "Reporting sheet",
            "Campaign audit checklist",
        ],
        "qa": [
            {
                "question": "Do you cover strategy or only setup?",
                "answer": "Both. The program moves from offer and message to audience, creative, reporting, and optimization.",
            },
            {
                "question": "Can agencies use this?",
                "answer": "Yes. The reporting and audit sections are especially useful for client work.",
            },
        ],
        "modules": [
            {
                "title": "Offer and audience fit",
                "duration": "1h 15m",
                "lessons": [
                    {"title": "Clarifying the conversion goal", "duration": "13:10", "type": "video", "free": True, "done": True},
                    {"title": "Audience research that informs creative", "duration": "17:35", "type": "video"},
                    {"title": "Offer worksheet", "duration": "PDF", "type": "pdf"},
                ],
            },
            {
                "title": "Campaign build and testing",
                "duration": "2h 00m",
                "lessons": [
                    {"title": "Ad set structure that stays manageable", "duration": "21:40", "type": "video"},
                    {"title": "Creative testing without chaos", "duration": "23:10", "type": "video"},
                    {"title": "Budget pacing", "duration": "14:35", "type": "video"},
                ],
            },
            {
                "title": "Optimization and retargeting",
                "duration": "1h 35m",
                "lessons": [
                    {"title": "Reading early signals correctly", "duration": "16:50", "type": "video"},
                    {"title": "Retargeting with better message sequencing", "duration": "18:20", "type": "video"},
                ],
            },
            {
                "title": "Reporting and scale",
                "duration": "50m",
                "lessons": [
                    {"title": "Client-ready reporting cadence", "duration": "11:15", "type": "video"},
                    {"title": "Scale triggers and warning signs", "duration": "12:40", "type": "video"},
                ],
            },
        ],
    },
    "design": {
        "label": "Graphic Design",
        "badgeClass": "badge-violet",
        "requirements": [
            "A willingness to share and revise your work",
            "Basic comfort with design software",
            "Curiosity about layout, typography, and systems",
        ],
        "learn": [
            "Design with stronger hierarchy and contrast",
            "Build brand assets with repeatable systems",
            "Create social, web, and presentation graphics",
            "Communicate design decisions more clearly",
            "Prepare source files for collaborators or clients",
        ],
        "resources": [
            "Layout starter kit",
            "Type pairing sheet",
            "Feedback checklist",
        ],
        "qa": [
            {
                "question": "Will this help with client work?",
                "answer": "Yes. The workflow emphasizes clarity, revisions, source hygiene, and reusable systems.",
            },
            {
                "question": "Do I need to be artistic already?",
                "answer": "No. The course focuses on structure, hierarchy, consistency, and iteration.",
            },
        ],
        "modules": [
            {
                "title": "Principles and foundations",
                "duration": "1h 10m",
                "lessons": [
                    {"title": "Hierarchy, spacing, and rhythm", "duration": "14:05", "type": "video", "free": True, "done": True},
                    {"title": "Color and contrast with intention", "duration": "15:40", "type": "video"},
                    {"title": "Design review guide", "duration": "PDF", "type": "pdf"},
                ],
            },
            {
                "title": "Brand systems",
                "duration": "1h 50m",
                "lessons": [
                    {"title": "Logo systems and lockups", "duration": "18:20", "type": "video"},
                    {"title": "Type choices that actually fit the brand", "duration": "21:10", "type": "video"},
                    {"title": "Reusable asset packs", "duration": "16:40", "type": "video"},
                ],
            },
            {
                "title": "Campaign and content design",
                "duration": "1h 35m",
                "lessons": [
                    {"title": "Designing social assets at speed", "duration": "17:45", "type": "video"},
                    {"title": "Landing page hero composition", "duration": "19:30", "type": "video"},
                ],
            },
            {
                "title": "Presentation and handoff",
                "duration": "55m",
                "lessons": [
                    {"title": "Presenting your work to non-designers", "duration": "12:10", "type": "video"},
                    {"title": "Export and source file hygiene", "duration": "11:55", "type": "video"},
                ],
            },
        ],
    },
    "social": {
        "label": "Social Media",
        "badgeClass": "badge-violet",
        "requirements": [
            "A niche, brand, or creator account to apply the ideas to",
            "Consistency over perfection",
            "Comfort testing content in public",
        ],
        "learn": [
            "Plan content around audience behavior",
            "Turn casual viewers into warm leads",
            "Build repeatable short-form content systems",
            "Analyze retention instead of vanity metrics",
            "Create a sustainable publishing workflow",
        ],
        "resources": [
            "Weekly planner",
            "Hook library",
            "Content scorecard",
        ],
        "qa": [
            {
                "question": "Is this only for creators?",
                "answer": "No. Service businesses, agencies, and educators can all use the planning and growth systems.",
            },
            {
                "question": "Do you cover analytics?",
                "answer": "Yes. The scorecard and review loops are designed to help you improve every week.",
            },
        ],
        "modules": [
            {
                "title": "Positioning and planning",
                "duration": "1h 00m",
                "lessons": [
                    {"title": "Profile clarity and audience promise", "duration": "11:10", "type": "video", "free": True, "done": True},
                    {"title": "Weekly content planning system", "duration": "13:30", "type": "video"},
                    {"title": "Planning board template", "duration": "PDF", "type": "pdf"},
                ],
            },
            {
                "title": "Hooks and retention",
                "duration": "1h 40m",
                "lessons": [
                    {"title": "Stronger first-line hooks", "duration": "14:45", "type": "video"},
                    {"title": "Retaining attention through structure", "duration": "18:10", "type": "video"},
                    {"title": "Editing for short-form flow", "duration": "17:50", "type": "video"},
                ],
            },
            {
                "title": "Growth loops and offers",
                "duration": "1h 25m",
                "lessons": [
                    {"title": "Turning engagement into inquiries", "duration": "15:20", "type": "video"},
                    {"title": "Soft CTAs that still convert", "duration": "12:45", "type": "video"},
                ],
            },
            {
                "title": "Review and iteration",
                "duration": "45m",
                "lessons": [
                    {"title": "Weekly analytics review", "duration": "11:50", "type": "video"},
                    {"title": "Content retrospective quiz", "duration": "8 min", "type": "quiz"},
                ],
            },
        ],
    },
}


def get_category_gradient(category: str) -> str:
    return {
        "ai": "linear-gradient(135deg,#1a0a2e,#2d1b69)",
        "forex": "linear-gradient(135deg,#0f2817,#1a4228)",
        "video": "linear-gradient(135deg,#1a0808,#3d1515)",
        "ads": "linear-gradient(135deg,#1a1008,#3d2e10)",
        "design": "linear-gradient(135deg,#0a0a1f,#1f1040)",
        "social": "linear-gradient(135deg,#1a0a1f,#2d0d35)",
    }.get(category, "linear-gradient(135deg,#111827,#1f2937)")


def get_category_mark(category: str) -> str:
    return {
        "ai": "AI",
        "forex": "FX",
        "video": "VE",
        "ads": "AD",
        "design": "GD",
        "social": "SM",
    }.get(category, "CR")


def escape_svg(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def create_course_thumbnail_data(course: dict[str, Any]) -> str:
    category = CATEGORY_LIBRARY.get(course.get("cat"), {"label": "SkillForge"})
    colors = {
        "ai": ["#130722", "#5336e2"],
        "forex": ["#0b2512", "#22c55e"],
        "video": ["#210808", "#ef4444"],
        "ads": ["#201204", "#f59e0b"],
        "design": ["#090b20", "#7c5cfc"],
        "social": ["#1b0c1d", "#ec4899"],
    }.get(course.get("cat"), ["#111827", "#334155"])
    raw_lines = []
    title = str(course.get("title", "SkillForge"))
    while title:
        raw_lines.append(title[:22].strip())
        title = title[22:]
    title_lines = raw_lines[:3] or [str(course.get("title", "SkillForge"))]
    tspans = "".join(
        f'<tspan x="88" dy="{0 if index == 0 else 58}">{escape_svg(line)}</tspan>'
        for index, line in enumerate(title_lines)
    )
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="{colors[0]}"/>
          <stop offset="100%" stop-color="{colors[1]}"/>
        </linearGradient>
      </defs>
      <rect width="1280" height="720" rx="42" fill="url(#bg)"/>
      <circle cx="1080" cy="120" r="190" fill="rgba(255,255,255,0.08)"/>
      <circle cx="180" cy="610" r="220" fill="rgba(255,255,255,0.06)"/>
      <text x="88" y="110" fill="#F0A500" font-family="Arial, sans-serif" font-size="34" font-weight="700">SkillForge Academy</text>
      <text x="88" y="196" fill="#EEF0F7" font-family="Arial, sans-serif" font-size="76" font-weight="800">{escape_svg(get_category_mark(course.get("cat")))}</text>
      <text x="88" y="266" fill="#F7F7FB" font-family="Arial, sans-serif" font-size="48" font-weight="700">{tspans}</text>
      <text x="88" y="500" fill="rgba(238,240,247,0.82)" font-family="Arial, sans-serif" font-size="28">{escape_svg(category["label"])}</text>
      <text x="88" y="548" fill="rgba(238,240,247,0.62)" font-family="Arial, sans-serif" font-size="24">Instructor: {escape_svg(course.get("instructor", "SkillForge"))}</text>
      <rect x="920" y="520" width="260" height="110" rx="26" fill="rgba(8,8,15,0.2)" stroke="rgba(255,255,255,0.18)"/>
      <text x="950" y="580" fill="#EEF0F7" font-family="Arial, sans-serif" font-size="42" font-weight="700">{escape_svg(course.get("price", "0"))} ETB</text>
    </svg>
    """.strip()
    return "data:image/svg+xml;charset=UTF-8," + quote(svg)


def with_lesson_metadata(course_id: str, modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hydrated = []
    for module_index, module in enumerate(modules, start=1):
        next_module = clone_json(module)
        next_lessons = []
        for lesson_index, lesson in enumerate(next_module.get("lessons", []), start=1):
            next_lesson = clone_json(lesson)
            next_lesson["id"] = f"{course_id}-m{module_index}-l{lesson_index}"
            next_lessons.append(next_lesson)
        next_module["lessons"] = next_lessons
        hydrated.append(next_module)
    return hydrated


def enrich_course(course: dict[str, Any], thumbnail_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    category = CATEGORY_LIBRARY.get(course.get("cat"), CATEGORY_LIBRARY["ai"])
    thumbnail_overrides = thumbnail_overrides or {}
    enriched = clone_json(course)
    enriched["mark"] = enriched.get("mark") or get_category_mark(enriched.get("cat"))
    enriched["gradient"] = enriched.get("gradient") or get_category_gradient(enriched.get("cat"))
    enriched["badgeClass"] = enriched.get("badgeClass") or category["badgeClass"]
    enriched["reviewLabel"] = enriched.get("reviewLabel") or (format_compact(enriched.get("reviews", 0)) if enriched.get("reviews") else "New")
    enriched["studentsLabel"] = enriched.get("studentsLabel") or format_number(enriched.get("students", 0))
    enriched["price"] = enriched.get("price") or format_number(enriched.get("priceValue", 0))
    enriched["orig"] = enriched.get("orig") or format_number(max(enriched.get("priceValue", 0), round(enriched.get("priceValue", 0) * 1.6)))
    enriched["thumbnail"] = enriched.get("thumbnail") or thumbnail_overrides.get(enriched["id"]) or create_course_thumbnail_data(enriched)
    enriched["track"] = category["label"]
    enriched["requirements"] = clone_json(category["requirements"])
    enriched["learn"] = clone_json(category["learn"])
    enriched["resources"] = clone_json(category["resources"])
    enriched["qa"] = clone_json(category["qa"])
    enriched["modules"] = with_lesson_metadata(enriched["id"], clone_json(category["modules"]))
    return enriched


def get_catalog_courses(store: dict[str, Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for course in store.get("courses", {}).get("base", []):
        merged[course["id"]] = course
    for course in store.get("courses", {}).get("custom", []):
        merged[course["id"]] = course
    thumbnail_overrides = store.get("courses", {}).get("thumbnailOverrides", {})
    return [enrich_course(course, thumbnail_overrides) for course in merged.values()]


def find_course_by_id(store: dict[str, Any], course_id: str) -> dict[str, Any] | None:
    for course in get_catalog_courses(store):
        if course["id"] == course_id:
            return course
    return None


def build_tutor_reply(prompt: str, course: dict[str, Any] | None = None) -> str:
    normalized = str(prompt or "").lower()
    track = str((course or {}).get("track", "AI Engineering")).lower()
    if "api" in normalized or "tool" in normalized or "automation" in normalized:
        return "Start by defining one job, one input shape, one output shape, and one clear failure path. That keeps the first backend integration simple and production-safe."
    if "client" in normalized or "sell" in normalized or "portfolio" in normalized:
        return "Turn this into a portfolio piece by solving one narrow, visible problem end to end, then document the before, after, and business result."
    if "beginner" in normalized or "start" in normalized:
        return "Begin with the first module, finish one practice exercise, and only then move into the automation or optimization layers. Momentum matters more than breadth."
    return f"Focus on the next concrete step inside {track}: finish the current lesson, practice one repeatable workflow, and write down what you would automate or improve next."


def normalize_course_input(source: dict[str, Any], existing_course: dict[str, Any] | None = None) -> dict[str, Any]:
    existing_course = existing_course or {}
    category = source.get("cat") if source.get("cat") in CATEGORY_LIBRARY else existing_course.get("cat", "ai")
    price_value = int("".join(char for char in str(source.get("priceValue", source.get("price", "0"))) if char.isdigit()) or "0")
    lessons = max(1, int(source.get("lessons", existing_course.get("lessons", 12)) or 12))
    hours = max(1, int(source.get("hours", existing_course.get("hours", 6)) or 6))
    rating = min(5, max(0, float(source.get("rating", existing_course.get("rating", 4.8)) or 4.8)))
    reviews = max(0, int(source.get("reviews", existing_course.get("reviews", 0)) or 0))
    students = max(0, int(source.get("students", existing_course.get("students", 0)) or 0))
    projects = max(1, int(source.get("projects", existing_course.get("projects", max(1, round(hours / 3)))) or 1))
    current = datetime.utcnow()
    return {
        **existing_course,
        "id": str(source.get("id", existing_course.get("id", ""))).strip(),
        "cat": category,
        "mark": get_category_mark(category),
        "title": str(source.get("title", existing_course.get("title", ""))).strip(),
        "instructor": str(source.get("instructor", existing_course.get("instructor", "Yonas Tesfaye"))).strip(),
        "rating": rating,
        "reviews": reviews,
        "reviewLabel": str(source.get("reviewLabel", format_compact(reviews) if reviews else "New")),
        "students": students,
        "studentsLabel": str(source.get("studentsLabel", format_number(students))),
        "price": format_number(price_value),
        "priceValue": price_value,
        "orig": str(source.get("orig", format_number(max(price_value, round(price_value * 1.6))))),
        "badge": str(source.get("badge", existing_course.get("badge", "Draft"))),
        "badgeClass": CATEGORY_LIBRARY[category]["badgeClass"],
        "lessons": lessons,
        "hours": hours,
        "level": str(source.get("level", existing_course.get("level", "Beginner"))),
        "updated": str(source.get("updated", month_year_label(current))),
        "updatedSort": int(source.get("updatedSort", month_sort_stamp(current))),
        "projects": projects,
        "gradient": str(source.get("gradient", get_category_gradient(category))),
        "overview": str(source.get("overview", existing_course.get("overview", ""))).strip(),
        "thumbnail": str(source.get("thumbnail", existing_course.get("thumbnail", ""))).strip(),
    }
