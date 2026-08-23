"""Populates the database with believable demo data.

Run via `make seed` (or `uv run python -m scripts.seed`). Safe to run more
than once — it exits early if any organization already exists, rather than
piling up duplicate demo orgs.
"""

import asyncio
import random

from faker import Faker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import async_session_factory
from app.models.comment import Comment
from app.models.enums import OrgRole, TaskPriority, TaskStatus
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.models.user import User

fake = Faker()

DEMO_PASSWORD = "demo-password-123"
ORG_COUNT = 3
PROJECTS_PER_ORG = (2, 3)
TASKS_PER_PROJECT = (5, 12)
COMMENTS_PER_TASK = (0, 4)


async def _seed_organization(session: AsyncSession, index: int) -> None:
    company = fake.company()
    org = Organization(name=company, slug=f"{fake.slug()}-{index}")
    session.add(org)
    await session.flush()

    owner = User(
        organization_id=org.id,
        email=f"owner{index}@example.com",
        hashed_password=hash_password(DEMO_PASSWORD),
        full_name=fake.name(),
        role=OrgRole.OWNER,
        is_active=True,
        is_email_verified=True,
    )
    session.add(owner)

    members = [owner]
    for role, count in [(OrgRole.ADMIN, 2), (OrgRole.MEMBER, 5)]:
        for _ in range(count):
            user = User(
                organization_id=org.id,
                email=fake.unique.email(),
                hashed_password=hash_password(DEMO_PASSWORD),
                full_name=fake.name(),
                role=role,
                is_active=True,
                is_email_verified=fake.boolean(chance_of_getting_true=70),
            )
            session.add(user)
            members.append(user)
    await session.flush()

    for _ in range(random.randint(*PROJECTS_PER_ORG)):
        project = Project(
            organization_id=org.id,
            created_by_id=random.choice(members).id,
            name=fake.catch_phrase(),
            description=fake.paragraph(nb_sentences=3),
        )
        session.add(project)
        await session.flush()

        for _ in range(random.randint(*TASKS_PER_PROJECT)):
            creator = random.choice(members)
            assignee = random.choice([*members, None])
            task = Task(
                organization_id=org.id,
                project_id=project.id,
                created_by_id=creator.id,
                assignee_id=assignee.id if assignee else None,
                title=fake.sentence(nb_words=6).rstrip("."),
                description=fake.paragraph(nb_sentences=2),
                status=random.choice(list(TaskStatus)),
                priority=random.choice(list(TaskPriority)),
                due_date=fake.date_between(start_date="-10d", end_date="+30d")
                if fake.boolean(chance_of_getting_true=60)
                else None,
            )
            session.add(task)
            await session.flush()

            for _ in range(random.randint(*COMMENTS_PER_TASK)):
                session.add(
                    Comment(
                        organization_id=org.id,
                        task_id=task.id,
                        author_id=random.choice(members).id,
                        body=fake.paragraph(nb_sentences=1),
                    )
                )

    print(f"  seeded '{company}' — login as owner{index}@example.com / {DEMO_PASSWORD}")


async def main() -> None:
    async with async_session_factory() as session:
        existing = await session.execute(select(Organization.id).limit(1))
        if existing.scalar_one_or_none() is not None:
            print("Database already has data — skipping seed. (Reset the DB to re-seed.)")
            return

        print(f"Seeding {ORG_COUNT} demo organizations...")
        for i in range(1, ORG_COUNT + 1):
            await _seed_organization(session, i)
        await session.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
