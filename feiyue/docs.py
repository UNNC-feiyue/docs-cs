import json
import os.path
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader
from pypinyin import lazy_pinyin

WORKING_DIR = Path.cwd()


def build_pages(records: list[dict], image_links: dict, templates: str, resources: str, output: str) -> None:
    mkdocs = MkDocs(templates, resources, output)
    mkdocs.pre_build(records)
    print("Pre-build complete")
    mkdocs.build_applicants()
    print("Generated applicant pages")
    mkdocs.build_programs()
    print("Generated program pages")
    mkdocs.build_nav()
    print("Generated mkdocs.yml and homepage")
    mkdocs.copy_resources()
    print("Copied mkdocs resources")
    if image_links:
        mkdocs.download(image_links)
        print("Downloaded referenced images")


class MkDocs:
    def __init__(self, templates: str, resources: str, output: str) -> None:
        self.templates_dir: Path = WORKING_DIR / templates
        self.resources_dir: Path = WORKING_DIR / resources
        self.output_dir: Path = WORKING_DIR / output
        self.docs_path: Path = self.output_dir / "docs"
        self.universities = None
        self.programs = None
        self.students = None
        self.applications = None
        self.env = None

    def pre_build(self, records: list[dict]) -> None:
        if not self.templates_dir.exists():
            raise FileNotFoundError(f"Template directory does not exist")
        if not self.resources_dir.exists():
            raise FileNotFoundError(f"Resources directory does not exist")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.docs_path.mkdir(parents=True, exist_ok=True)

        self.universities = records[0]
        self.programs = records[1]
        self.students = records[2]
        self.applications = records[3]

        # Helper dicts to simplify rendering
        students_by_term = defaultdict(list)
        for student in self.students.values():
            students_by_term[student["term"]].append(student)

        def sort_key(value: dict) -> tuple[int, str | list[str]]:
            name = value["name"]
            if re.match(r'^[A-Za-z]', name):
                return 0, name.lower()
            else:
                return 1, lazy_pinyin(name)

        students_by_term = {
            term: sorted(students, key=sort_key)  # Sort by student name
            for term, students in sorted(students_by_term.items(), reverse=True)  # Sort by term descending
        }

        universities_by_region = defaultdict(list)
        for university in self.universities.values():
            universities_by_region[university["region"]].append(university)
        universities_by_region = {
            region: sorted(universities, key=lambda u: u["name"])  # Sort by university name
            for region, universities in sorted(
                universities_by_region.items(),
                key=lambda item: (-len(item[1]), item[0])  # Sort by COUNT(universities) descending, then region name
            )
        }
        for universities in universities_by_region.values():
            for university in universities:
                university["programs"].sort(key=lambda p: p["display_value"])  # Sort by program abbreviation

        self.env = Environment(loader=FileSystemLoader(self.templates_dir))
        self.env.globals.update({  # Jinja global variables
            "current_year": datetime.now().year,
            "universities": self.universities,
            "programs": self.programs,
            "students": self.students,
            "applications": self.applications,
            "status": {
                "Admit": ":green_circle: Admit",
                "Reject": ":red_circle: Reject",
                "Waitlist": ":yellow_circle: Waitlist",
                "Chosen": ":checkered_flag: Chosen",
            },
            "students_by_term": students_by_term,
            "universities_by_region": universities_by_region
        })

    def build_applicants(self) -> None:
        applicants_dir = self.docs_path / "applicants"
        applicants_dir.mkdir(exist_ok=True)

        # Individual applicant pages
        for student in self.students.values():
            template = self.env.get_template("applicant.jinja")
            output = template.render(
                student=student
            )
            with open(applicants_dir / f"{student['s_id']}.md", "w") as f:
                f.write(output)

        # Applicants index page
        template_index = self.env.get_template("applicant_index.jinja")
        output = template_index.render()
        with open(applicants_dir / "index.md", "w") as f:
            f.write(output)

    def build_programs(self) -> None:
        programs_dir = self.docs_path / "programs"
        programs_dir.mkdir(exist_ok=True)

        # Individual program pages
        for program in self.programs.values():
            # Helper list for correctly sorting applications_by_term
            program_applications = []
            for application in self.applications.values():
                if application["program"][0]["row_id"] == program["_id"]:
                    student = self.students[application["student"][0]["row_id"]]
                    program_applications.append((student["term"], student["name"], application))
            program_applications.sort(key=lambda x: x[1].lower())  # Sort by student name
            program_applications.sort(key=lambda x: x[0], reverse=True)  # Sort by term descending

            applications_by_term = defaultdict(list)
            for term, _, application in program_applications:
                applications_by_term[term].append(application)

            template = self.env.get_template("program.jinja")
            output = template.render(
                program=program,
                applications_by_term=applications_by_term
            )
            with open(programs_dir / f"{program['p_id']}.md", "w") as f:
                f.write(output)

        # Programs index page
        template_index = self.env.get_template("program_index.jinja")
        output = template_index.render()
        with open(programs_dir / "index.md", "w") as f:
            f.write(output)

    def build_nav(self) -> None:
        # mkdocs.yml
        template = self.env.get_template("mkdocs.jinja")
        output = template.render()
        with open(self.output_dir / "mkdocs.yml", "w") as f:
            f.write(output)

        # Homepage
        template_index = self.env.get_template("index.jinja")
        output = template_index.render()
        with open(self.docs_path / "index.md", "w") as f:
            f.write(output)

    def copy_resources(self) -> None:
        with open(self.resources_dir / "manifest.json", "r") as f:
            manifest = json.load(f)

        for src, dest in manifest.items():
            if os.path.isfile(self.resources_dir / src):
                shutil.copy(self.resources_dir / src, self.output_dir / dest)
            elif os.path.isdir(self.resources_dir / src):
                shutil.copytree(self.resources_dir / src, self.output_dir / dest, dirs_exist_ok=True)

    def download(self, image_links: dict) -> None:
        images_dir = self.docs_path / "images"
        images_dir.mkdir(exist_ok=True)

        for filename, data in image_links.items():
            url = data["download_link"]
            if not url:
                print(f"NO DOWNLOAD LINK FOR {filename}, SKIPPING")
                continue

            response = requests.get(url, stream=True)
            if response.status_code != 200:
                raise Exception(f"Failed to download {filename} from {url}: {response.status_code} {response.text}")

            with open(images_dir / filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
