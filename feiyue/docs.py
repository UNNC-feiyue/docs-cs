from pathlib import Path

from jinja2 import Environment, FileSystemLoader

WORKING_DIR = Path.cwd()


def build_pages(records: list[dict], template: str, resources: str, output: str) -> None:
    mkdocs = MkDocs(template, resources, output)
    mkdocs.pre_build(records)
    mkdocs.build_applicants()


class MkDocs:
    def __init__(self, template: str, resources: str, output: str):
        self.template_path: Path = WORKING_DIR / template
        self.resources_path: Path = WORKING_DIR / resources
        self.output_path: Path = WORKING_DIR / output
        self.universities = None
        self.programs = None
        self.students = None
        self.applications = None
        self.env = None

    def pre_build(self, records: list[dict]) -> None:
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template directory does not exist")
        if not self.resources_path.exists():
            raise FileNotFoundError(f"Resources directory does not exist")
        self.output_path.mkdir(parents=True, exist_ok=True)

        self.universities = records[0]
        self.programs = records[1]
        self.students = records[2]
        self.applications = records[3]

        self.env = Environment(loader=FileSystemLoader(self.template_path))
        self.env.globals.update({ # Jinja global variables
            "universities": self.universities,
            "programs": self.programs,
            "students": self.students,
            "applications": self.applications,
            "status": {
                "Admit": ":green_circle: Admit",
                "Reject": ":red_circle: Reject",
                "Waitlist": ":yellow_circle: Waitlist",
                "Chosen": ":white_check_mark: Chosen",
            }
        })

    def build_applicants(self):
        applicants_path = self.output_path / "applicants"
        applicants_path.mkdir(exist_ok=True)

        for _, student in self.students.items():
            template = self.env.get_template("applicant.jinja")
            output = template.render(student=student)
            with open(applicants_path / f"{student['s_id']}.md", "w") as f:
                f.write(output)
