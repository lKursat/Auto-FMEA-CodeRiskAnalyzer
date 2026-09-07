"""
test_dependency_graph.py — Unit tests for the dependency graph module.
=====================================================================
Tests fan-in detection across Python, Java, and C# using real temp files,
and tests project-wide duplicate class detection.

All temp files are created in setUp and cleaned up in tearDown.
"""

import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dependency_graph import build_dependency_map, find_duplicates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_dir():
    """Create a temporary directory for test project files."""
    return tempfile.mkdtemp(prefix="fmea_test_")


def _write_file(directory, filename, content):
    """Write a file into the given directory and return its absolute path."""
    path = os.path.join(directory, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


# ===========================================================================
# Python fan-in tests
# ===========================================================================

class TestFanInPython(unittest.TestCase):
    """Test fan-in detection for Python source files."""

    def setUp(self):
        """Create a temp directory to act as a mini project root."""
        self.project_dir = _make_temp_dir()

    def tearDown(self):
        """Remove all temp files after each test."""
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_no_dependents(self):
        """A class with no other file referencing it should have fan_in=0."""
        _write_file(self.project_dir, "target.py", (
            "class TargetClass:\n"
            "    def do_something(self):\n"
            "        pass\n"
        ))
        _write_file(self.project_dir, "unrelated.py", (
            "class UnrelatedClass:\n"
            "    def work(self):\n"
            "        return 42\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "python",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "target.py"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 0)

    def test_instantiation_detected(self):
        """Another file doing 'self.x = TargetClass()' should count as fan_in=1."""
        _write_file(self.project_dir, "target.py", (
            "class TargetClass:\n"
            "    def run(self):\n"
            "        pass\n"
        ))
        _write_file(self.project_dir, "consumer.py", (
            "class ConsumerClass:\n"
            "    def setup(self):\n"
            "        self.x = TargetClass()\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "python",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "target.py"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 1)

    def test_import_detected(self):
        """'from module import TargetClass' in another file should count as fan_in=1."""
        _write_file(self.project_dir, "target.py", (
            "class TargetClass:\n"
            "    def run(self):\n"
            "        pass\n"
        ))
        _write_file(self.project_dir, "consumer.py", (
            "from target import TargetClass\n"
            "\n"
            "class AnotherClass:\n"
            "    def work(self):\n"
            "        pass\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "python",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "target.py"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 1)

    def test_multiple_dependents(self):
        """3 separate files all instantiate TargetClass → fan_in=3."""
        _write_file(self.project_dir, "target.py", (
            "class TargetClass:\n"
            "    def run(self):\n"
            "        pass\n"
        ))
        for i in range(3):
            _write_file(self.project_dir, f"consumer_{i}.py", (
                f"class Consumer{i}:\n"
                f"    def go(self):\n"
                f"        obj = TargetClass()\n"
            ))
        dep_map = build_dependency_map(
            self.project_dir, "python",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "target.py"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 3)

    def test_affected_classes_list(self):
        """fan_in=2 from two different files, affected_classes must list both class names."""
        _write_file(self.project_dir, "target.py", (
            "class TargetClass:\n"
            "    def run(self):\n"
            "        pass\n"
        ))
        _write_file(self.project_dir, "alpha.py", (
            "class AlphaClient:\n"
            "    def go(self):\n"
            "        obj = TargetClass()\n"
        ))
        _write_file(self.project_dir, "beta.py", (
            "class BetaClient:\n"
            "    def go(self):\n"
            "        obj = TargetClass()\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "python",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "target.py"),
        )
        affected = dep_map["TargetClass"]["affected_classes"]
        self.assertIn("AlphaClient", affected)
        self.assertIn("BetaClient", affected)
        self.assertEqual(len(affected), 2)

    def test_self_reference_ignored(self):
        """A class referencing itself (e.g. recursive call) must NOT count as fan_in."""
        _write_file(self.project_dir, "target.py", (
            "class TargetClass:\n"
            "    def recurse(self):\n"
            "        return TargetClass()\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "python",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "target.py"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 0)


# ===========================================================================
# Java fan-in tests
# ===========================================================================

class TestFanInJava(unittest.TestCase):
    """Test fan-in detection for Java source files."""

    def setUp(self):
        self.project_dir = _make_temp_dir()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_instantiation_detected(self):
        """'new TargetClass(' in another .java file → fan_in=1."""
        _write_file(self.project_dir, "TargetClass.java", (
            "public class TargetClass {\n"
            "    public void run() {}\n"
            "}\n"
        ))
        _write_file(self.project_dir, "Consumer.java", (
            "public class Consumer {\n"
            "    public void go() {\n"
            "        TargetClass t = new TargetClass();\n"
            "    }\n"
            "}\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "java",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "TargetClass.java"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 1)

    def test_extends_detected(self):
        """'extends TargetClass' in another .java file → fan_in=1."""
        _write_file(self.project_dir, "TargetClass.java", (
            "public class TargetClass {\n"
            "    public void run() {}\n"
            "}\n"
        ))
        _write_file(self.project_dir, "ChildClass.java", (
            "public class ChildClass extends TargetClass {\n"
            "    public void extra() {}\n"
            "}\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "java",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "TargetClass.java"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 1)

    def test_import_detected(self):
        """'import com.example.TargetClass;' in another file → fan_in=1."""
        _write_file(self.project_dir, "TargetClass.java", (
            "public class TargetClass {\n"
            "    public void run() {}\n"
            "}\n"
        ))
        _write_file(self.project_dir, "Importer.java", (
            "import com.example.TargetClass;\n"
            "\n"
            "public class Importer {\n"
            "    public void use() {}\n"
            "}\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "java",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "TargetClass.java"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 1)

    def test_no_dependents(self):
        """An isolated Java class with no references from others → fan_in=0."""
        _write_file(self.project_dir, "TargetClass.java", (
            "public class TargetClass {\n"
            "    public void run() {}\n"
            "}\n"
        ))
        _write_file(self.project_dir, "Other.java", (
            "public class Other {\n"
            "    public void work() {}\n"
            "}\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "java",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "TargetClass.java"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 0)


# ===========================================================================
# C# fan-in tests
# ===========================================================================

class TestFanInCSharp(unittest.TestCase):
    """Test fan-in detection for C# source files."""

    def setUp(self):
        self.project_dir = _make_temp_dir()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_instantiation_detected(self):
        """'new TargetClass(' in another .cs file → fan_in=1."""
        _write_file(self.project_dir, "TargetClass.cs", (
            "public class TargetClass {\n"
            "    public void Run() {}\n"
            "}\n"
        ))
        _write_file(self.project_dir, "Consumer.cs", (
            "public class Consumer {\n"
            "    public void Go() {\n"
            "        var t = new TargetClass();\n"
            "    }\n"
            "}\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "csharp",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "TargetClass.cs"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 1)

    def test_inheritance_detected(self):
        """': TargetClass' (C# inheritance) in another .cs file → fan_in=1."""
        _write_file(self.project_dir, "TargetClass.cs", (
            "public class TargetClass {\n"
            "    public void Run() {}\n"
            "}\n"
        ))
        _write_file(self.project_dir, "ChildClass.cs", (
            "public class ChildClass : TargetClass {\n"
            "    public void Extra() {}\n"
            "}\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "csharp",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "TargetClass.cs"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 1)

    def test_no_dependents(self):
        """An isolated C# class with no references from others → fan_in=0."""
        _write_file(self.project_dir, "TargetClass.cs", (
            "public class TargetClass {\n"
            "    public void Run() {}\n"
            "}\n"
        ))
        _write_file(self.project_dir, "Other.cs", (
            "public class Other {\n"
            "    public void Work() {}\n"
            "}\n"
        ))
        dep_map = build_dependency_map(
            self.project_dir, "csharp",
            primary_classes=["TargetClass"],
            primary_file=os.path.join(self.project_dir, "TargetClass.cs"),
        )
        self.assertEqual(dep_map["TargetClass"]["fan_in"], 0)


# ===========================================================================
# Duplicate class detection tests
# ===========================================================================

class TestDuplicateDetection(unittest.TestCase):
    """Test project-wide duplicate class name detection."""

    def setUp(self):
        self.project_dir = _make_temp_dir()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_duplicate_same_file(self):
        """Two classes named 'Foo' in the same .py file → both flagged as duplicate."""
        _write_file(self.project_dir, "stuff.py", (
            "class Foo:\n"
            "    def a(self):\n"
            "        pass\n"
            "\n"
            "class Bar:\n"
            "    def b(self):\n"
            "        pass\n"
            "\n"
            "class Foo:\n"
            "    def c(self):\n"
            "        pass\n"
        ))
        duplicates = find_duplicates(self.project_dir, "python")
        self.assertIn("Foo", duplicates)
        self.assertEqual(len(duplicates["Foo"]), 2)

    def test_duplicate_across_files(self):
        """'Foo' in file1.py and file2.py → flagged as duplicate."""
        _write_file(self.project_dir, "file1.py", (
            "class Foo:\n"
            "    def a(self):\n"
            "        pass\n"
        ))
        _write_file(self.project_dir, "file2.py", (
            "class Foo:\n"
            "    def b(self):\n"
            "        pass\n"
        ))
        duplicates = find_duplicates(self.project_dir, "python")
        self.assertIn("Foo", duplicates)
        self.assertEqual(len(duplicates["Foo"]), 2)

    def test_duplicate_across_languages(self):
        """'UserService' in both a .py and a .java file — only detected within same language scan."""
        # find_duplicates scans per-language, so same name in different languages
        # should NOT be flagged (each language is scanned independently).
        _write_file(self.project_dir, "service.py", (
            "class UserService:\n"
            "    def run(self):\n"
            "        pass\n"
        ))
        _write_file(self.project_dir, "Service.java", (
            "public class UserService {\n"
            "    public void run() {}\n"
            "}\n"
        ))
        py_dups = find_duplicates(self.project_dir, "python")
        java_dups = find_duplicates(self.project_dir, "java")
        # Each language only sees 1 instance → no duplicate within either language
        self.assertNotIn("UserService", py_dups)
        self.assertNotIn("UserService", java_dups)

    def test_no_duplicate(self):
        """All unique class names → no duplicates detected."""
        _write_file(self.project_dir, "a.py", (
            "class Alpha:\n"
            "    def run(self):\n"
            "        pass\n"
        ))
        _write_file(self.project_dir, "b.py", (
            "class Beta:\n"
            "    def run(self):\n"
            "        pass\n"
        ))
        duplicates = find_duplicates(self.project_dir, "python")
        self.assertEqual(len(duplicates), 0)

    def test_duplicate_location_info(self):
        """Duplicate entries must include 'file' (with path) and 'line' (integer) keys."""
        _write_file(self.project_dir, "a.py", (
            "class Widget:\n"
            "    def a(self):\n"
            "        pass\n"
        ))
        _write_file(self.project_dir, "b.py", (
            "class Widget:\n"
            "    def b(self):\n"
            "        pass\n"
        ))
        duplicates = find_duplicates(self.project_dir, "python")
        self.assertIn("Widget", duplicates)
        for loc in duplicates["Widget"]:
            self.assertIn("file", loc)
            self.assertIn("line", loc)
            self.assertIsInstance(loc["file"], str)
            self.assertIsInstance(loc["line"], int)
            self.assertTrue(len(loc["file"]) > 0)


if __name__ == "__main__":
    unittest.main()
