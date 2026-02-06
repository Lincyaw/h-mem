"""File system loader for SKILL.md files.

This module handles parsing SKILL.md files with YAML frontmatter
and loading skill content from the file system.
"""

from pathlib import Path
from typing import Any
from datetime import datetime, timezone

import yaml
import structlog

from hmem.skills.models import SkillMetadata, SkillContent

logger = structlog.get_logger()


class SkillLoader:
    """Loads and parses SKILL.md files from the file system.

    SKILL.md files use YAML frontmatter format:
    ```
    ---
    name: skill-name
    description: When to use this skill
    ...
    ---

    # Markdown Content
    ...
    ```
    """

    def __init__(self, base_path: Path | str):
        """Initialize skill loader.

        Args:
            base_path: Base path for skills directory (e.g., src/hmem/skills)
        """
        self.base_path = Path(base_path)
        self.meta_path = self.base_path / "_meta"
        self.generated_path = self.base_path / "generated"
        self.logger = logger.bind(component="skill_loader")

    def ensure_directories(self) -> None:
        """Ensure skills directories exist."""
        self.meta_path.mkdir(parents=True, exist_ok=True)
        self.generated_path.mkdir(parents=True, exist_ok=True)

    def parse_skill_file(self, file_path: Path) -> SkillContent | None:
        """Parse a SKILL.md file into SkillContent.

        Args:
            file_path: Path to the SKILL.md file

        Returns:
            SkillContent object or None if parsing fails
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            return self.parse_skill_content(content, str(file_path))
        except Exception as e:
            self.logger.error(
                "skill_file_read_failed", path=str(file_path), error=str(e)
            )
            return None

    def parse_skill_content(
        self, raw_content: str, file_path: str | None = None
    ) -> SkillContent | None:
        """Parse raw SKILL.md content string.

        Args:
            raw_content: Raw file content with YAML frontmatter
            file_path: Optional file path for metadata

        Returns:
            SkillContent object or None if parsing fails
        """
        try:
            # Split frontmatter from content
            if not raw_content.startswith("---"):
                self.logger.warning("skill_no_frontmatter", path=file_path)
                return None

            # Find the closing ---
            lines = raw_content.split("\n")
            frontmatter_end = -1
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    frontmatter_end = i
                    break

            if frontmatter_end == -1:
                self.logger.warning("skill_frontmatter_not_closed", path=file_path)
                return None

            # Parse YAML frontmatter
            frontmatter_text = "\n".join(lines[1:frontmatter_end])
            body_text = "\n".join(lines[frontmatter_end + 1 :]).strip()

            frontmatter_data = yaml.safe_load(frontmatter_text) or {}

            # Determine skill type from path
            skill_type = "generated"
            if file_path and "_meta" in file_path:
                skill_type = "meta"
                frontmatter_data["is_protected"] = True

            frontmatter_data["skill_type"] = skill_type
            frontmatter_data["file_path"] = file_path

            # Parse timestamps if present
            for ts_field in ["created_at", "updated_at"]:
                if ts_field in frontmatter_data and isinstance(
                    frontmatter_data[ts_field], str
                ):
                    try:
                        frontmatter_data[ts_field] = datetime.fromisoformat(
                            frontmatter_data[ts_field]
                        )
                    except ValueError:
                        pass

            # Create metadata
            metadata = SkillMetadata(**frontmatter_data)

            return SkillContent(metadata=metadata, content=body_text)

        except yaml.YAMLError as e:
            self.logger.error("skill_yaml_parse_failed", path=file_path, error=str(e))
            return None
        except Exception as e:
            self.logger.error("skill_parse_failed", path=file_path, error=str(e))
            return None

    def load_skill(self, skill_name: str) -> SkillContent | None:
        """Load a skill by name.

        Searches first in _meta/, then in generated/.

        Args:
            skill_name: Skill name (kebab-case)

        Returns:
            SkillContent or None if not found
        """
        # Try meta skills first
        meta_skill_path = self.meta_path / skill_name / "SKILL.md"
        if meta_skill_path.exists():
            return self.parse_skill_file(meta_skill_path)

        # Try generated skills
        generated_skill_path = self.generated_path / skill_name / "SKILL.md"
        if generated_skill_path.exists():
            return self.parse_skill_file(generated_skill_path)

        self.logger.debug("skill_not_found", name=skill_name)
        return None

    def list_all_skills(self, include_suspended: bool = False) -> list[SkillMetadata]:
        """List all available skills.

        Args:
            include_suspended: Include suspended skills in the list

        Returns:
            List of SkillMetadata objects
        """
        skills: list[SkillMetadata] = []

        # Load meta skills
        if self.meta_path.exists():
            for skill_dir in self.meta_path.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        content = self.parse_skill_file(skill_file)
                        if content and (
                            include_suspended or not content.metadata.is_suspended
                        ):
                            skills.append(content.metadata)

        # Load generated skills
        if self.generated_path.exists():
            for skill_dir in self.generated_path.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        content = self.parse_skill_file(skill_file)
                        if content and (
                            include_suspended or not content.metadata.is_suspended
                        ):
                            skills.append(content.metadata)

        return skills

    def list_meta_skills(self) -> list[SkillMetadata]:
        """List only meta (protected) skills.

        Returns:
            List of meta skill metadata
        """
        skills: list[SkillMetadata] = []

        if self.meta_path.exists():
            for skill_dir in self.meta_path.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        content = self.parse_skill_file(skill_file)
                        if content:
                            skills.append(content.metadata)

        return skills

    def skill_exists(self, skill_name: str) -> bool:
        """Check if a skill exists.

        Args:
            skill_name: Skill name to check

        Returns:
            True if skill exists
        """
        meta_path = self.meta_path / skill_name / "SKILL.md"
        generated_path = self.generated_path / skill_name / "SKILL.md"
        return meta_path.exists() or generated_path.exists()

    def get_skill_path(self, skill_name: str, skill_type: str = "generated") -> Path:
        """Get the path for a skill file.

        Args:
            skill_name: Skill name
            skill_type: "meta" or "generated"

        Returns:
            Path to the SKILL.md file
        """
        if skill_type == "meta":
            return self.meta_path / skill_name / "SKILL.md"
        return self.generated_path / skill_name / "SKILL.md"

    def write_skill(
        self,
        skill_name: str,
        metadata: dict[str, Any],
        content: str,
        skill_type: str = "generated",
    ) -> Path:
        """Write a skill file to disk.

        Args:
            skill_name: Skill name (kebab-case)
            metadata: YAML frontmatter data
            content: Markdown content body
            skill_type: "meta" or "generated"

        Returns:
            Path to the written file
        """
        # Determine directory
        if skill_type == "meta":
            skill_dir = self.meta_path / skill_name
        else:
            skill_dir = self.generated_path / skill_name

        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"

        # Format YAML frontmatter
        # Convert datetime objects to ISO strings
        metadata_copy = metadata.copy()
        for key, value in metadata_copy.items():
            if isinstance(value, datetime):
                metadata_copy[key] = value.isoformat()

        frontmatter = yaml.safe_dump(
            metadata_copy,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        # Write file
        file_content = f"---\n{frontmatter}---\n\n{content}"
        skill_file.write_text(file_content, encoding="utf-8")

        self.logger.info(
            "skill_written",
            name=skill_name,
            path=str(skill_file),
            skill_type=skill_type,
        )

        return skill_file

    def update_skill_metadata(self, skill_name: str, updates: dict[str, Any]) -> bool:
        """Update metadata fields in an existing skill file.

        Preserves the markdown content while updating frontmatter.

        Args:
            skill_name: Skill name
            updates: Dictionary of fields to update

        Returns:
            True if update successful
        """
        skill_content = self.load_skill(skill_name)
        if not skill_content:
            return False

        # Merge updates into existing metadata
        current_data = skill_content.metadata.model_dump()
        current_data.update(updates)
        current_data["updated_at"] = datetime.now(timezone.utc)

        # Determine skill type
        skill_type = skill_content.metadata.skill_type

        # Rewrite file
        self.write_skill(
            skill_name=skill_name,
            metadata=current_data,
            content=skill_content.content,
            skill_type=skill_type,
        )

        return True

    def delete_skill(self, skill_name: str, force: bool = False) -> bool:
        """Delete a skill from the file system.

        Args:
            skill_name: Skill name to delete
            force: If True, delete even protected skills

        Returns:
            True if deleted
        """
        skill_content = self.load_skill(skill_name)
        if not skill_content:
            return False

        if skill_content.metadata.is_protected and not force:
            self.logger.warning(
                "cannot_delete_protected_skill",
                name=skill_name,
            )
            return False

        # Determine path and delete
        file_path = skill_content.metadata.file_path
        if file_path:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                # Remove parent directory if empty
                parent = path.parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()

                self.logger.info("skill_deleted", name=skill_name)
                return True

        return False
