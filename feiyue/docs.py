from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from ruamel.yaml import YAML

WORKING_DIR = Path.cwd()


def build_pages(records: list[dict], template: str, resources: str, output: str) -> None:
    mkdocs = MkDocs(template, resources, output)
    mkdocs.pre_build(records)
    mkdocs.build_applicants()
    mkdocs.build_programs()
    mkdocs.build_nav()


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
                "Chosen": ":checkered_flag: Chosen",
            }
        })

    def build_applicants(self):
        applicants_path = self.output_path / "applicants"
        applicants_path.mkdir(exist_ok=True)

        # Individual applicant pages
        for student in self.students.values():
            template = self.env.get_template("applicant.jinja")
            output = template.render(
                student=student
            )
            with open(applicants_path / f"{student['s_id']}.md", "w") as f:
                f.write(output)

        # Applicants index page
        students_by_term = defaultdict(list)
        for student in self.students.values():
            students_by_term[student["term"]].append(student)

        template_index = self.env.get_template("applicant_index.jinja")
        output = template_index.render(
            students_by_term=students_by_term
        )
        with open(applicants_path / "index.md", "w") as f:
            f.write(output)

    def build_programs(self):
        programs_path = self.output_path / "programs"
        programs_path.mkdir(exist_ok=True)

        # Individual program pages
        for program in self.programs.values():
            # Group program applications by student terms
            applications_by_term = defaultdict(list)
            for application in self.applications.values():
                if application["program"][0]["row_id"] == program["_id"]:
                    student = self.students[application["student"][0]["row_id"]]
                    applications_by_term[student["term"]].append(application)

            template = self.env.get_template("program.jinja")
            output = template.render(
                program=program,
                applications_by_term=applications_by_term
            )
            with open(programs_path / f"{program['p_id']}.md", "w") as f:
                f.write(output)

        # Programs index page
        uni_by_region = defaultdict(list)
        for university in self.universities.values():
            uni_by_region[university["region"]].append(university)
        uni_by_region = dict(sorted(uni_by_region.items(), reverse=True))   # Sort in descending order

        template_index = self.env.get_template("program_index.jinja")
        output = template_index.render(
            uni_by_region=uni_by_region,
            programs=self.programs
        )
        with open(programs_path / "index.md", "w") as f:
            f.write(output)


    def build_nav(self):
        # Initialize nav structure
        nav = [
            {"Home": "index.md"},
            {"Applications": ["output/applicants/index.md"]},
            {"Programs": ["output/programs/index.md"]},
        ]

        # Group universities by region (sorted in reverse order)
        uni_by_region = defaultdict(list)
        for uni in self.universities.values():
            uni_by_region[uni["region"]].append(uni)
        
        program_table = {p["abbrv"]: p["p_id"] for p in self.programs.values()}

        # Create a nested structure for programs by region
        programs_by_region = {
            region: [
                {
                    uni["abbrv"]: [
                        {prog["display_value"]: f"output/programs/{program_table[prog['display_value']]}.md"}
                        for prog in sorted(uni["programs"], key=lambda p: p["display_value"])
                    ]
                }
                for uni in sorted(unis, key=lambda u: u["abbrv"])
            ]
            for region, unis in sorted(uni_by_region.items(), reverse=True)
        }

        # Update the nav structure with programs
        for item in nav:
            if "Programs" in item:
                for region, region_data in programs_by_region.items():
                    item["Programs"].append({region: region_data})
                break

        # Write the updated nav structure to mkdocs.yml
        yaml = YAML()
        yaml.preserve_quotes = True
        nav_path = WORKING_DIR / "mkdocs.yml"

        with open(nav_path, "r", encoding="utf-8") as f:
            config = yaml.load(f)

        config["nav"] = nav

        with open(nav_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)

