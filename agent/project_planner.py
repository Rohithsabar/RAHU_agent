from __future__ import annotations

from typing import List


class ProjectPlanner:
    def __init__(self) -> None:
        self.recommendations = [
            {
                "title": "Freelance Web Task",
                "description": "Offer small web design, landing page, or automation tasks for local clients.",
                "income_potential": "$50-$300 per project",
            },
            {
                "title": "AI Content Setup",
                "description": "Create short-form content, product descriptions, or social media scripts using AI tools.",
                "income_potential": "$100-$500 per month",
            },
            {
                "title": "Computer Support Service",
                "description": "Help people with laptop setup, software installation, backups, and troubleshooting.",
                "income_potential": "$20-$100 per task",
            },
            {
                "title": "Automation Workflow",
                "description": "Build repeatable templates for task automation, data scraping, or file processing.",
                "income_potential": "$150-$800 per project",
            },
        ]

    def get_recommendations(self) -> List[dict]:
        return self.recommendations

    def daily_plan(self) -> str:
        return (
            "Recommended daily workflow: spend 60 minutes on lead generation, 90 minutes on project work, "
            "30 minutes on follow-up, and 20 minutes on payment and client communication."
        )
