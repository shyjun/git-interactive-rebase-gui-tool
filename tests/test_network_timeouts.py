"""Network-facing GitWorker calls must use the extended timeout.

GitWorker's default (30s) is meant for local commands (git reset). A slow
remote or a big repo easily exceeds it, so fetch/pull/push/ls-remote pass
timeout=_NET_TIMEOUT explicitly - otherwise the operation is killed
mid-flight and surfaces as "Command timed out after 30s".

Runtime coverage for fetch/pull lives in test_pull_flow.py; this file AST-
guards every site, including push and ls-remote, which no test executes.
"""
import ast
import os
import unittest

_DIR = os.path.join(os.path.dirname(__file__), "..")
_MODULES = ("lib/app_window/reset_mixin.py", "lib/app_window/update_mixin.py",
            "lib/app_window/undo_mixin.py")
_NETWORK_SUBCOMMANDS = {"fetch", "pull", "push", "ls-remote"}


def _parse(relpath):
    with open(os.path.join(_DIR, relpath), encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=relpath)


def _string_constants(node):
    return {
        n.value for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def _is_network_call(node):
    """True when the GitWorker call's command is fetch/pull/push/ls-remote.

    The pull and push sites build their command into a local ``cmd`` variable,
    so a Name first argument counts as network; literal lists are classified
    by their subcommand.
    """
    if not node.args:
        return False
    first = node.args[0]
    if isinstance(first, ast.Name):
        return True
    if isinstance(first, (ast.List, ast.Tuple)):
        return bool(_string_constants(first) & _NETWORK_SUBCOMMANDS)
    return False


class TestNetworkTimeoutConstant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _parse("lib/app_window/workers.py")
        cls.init = None
        for node in ast.walk(cls.tree):
            if (isinstance(node, ast.ClassDef) and node.name == "GitWorker"):
                for item in node.body:
                    if (isinstance(item, ast.FunctionDef)
                            and item.name == "__init__"):
                        cls.init = item
                        break
        if cls.init is None:
            raise AssertionError("GitWorker.__init__ must exist")

    def test_net_timeout_exceeds_local_default(self):
        values = [
            n.value.value for n in ast.walk(self.tree)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_NET_TIMEOUT"
                    for t in n.targets)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, int)
        ]
        self.assertEqual(len(values), 1, "_NET_TIMEOUT must be defined once")
        self.assertGreater(values[0], 30,
                           "_NET_TIMEOUT must be longer than the local default")

    def test_local_default_stays_at_30(self):
        """Local commands (git reset) keep the tight default so a hang there
        is still surfaced quickly."""
        defaults = [
            d.value for d in self.init.args.defaults
            if isinstance(d, ast.Constant) and isinstance(d.value, int)
        ]
        self.assertIn(30, defaults,
                      "GitWorker's local default must stay 30s")


class TestNetworkCallSites(unittest.TestCase):
    """Every fetch/pull/push/ls-remote GitWorker call passes _NET_TIMEOUT."""

    @classmethod
    def setUpClass(cls):
        cls.sites = []
        for relpath in _MODULES:
            tree = _parse(relpath)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not (isinstance(node.func, ast.Name)
                        and node.func.id == "GitWorker"):
                    continue
                cls.sites.append((relpath, node.lineno, node))

    def test_network_sites_pass_net_timeout(self):
        network = [s for s in self.sites if _is_network_call(s[2])]
        self.assertEqual(
            len(network), 5,
            "expected 5 network sites (fetch x2, pull, push, ls-remote), "
            f"found {len(network)}: {[(p, ln) for p, ln, _ in network]}",
        )
        for relpath, lineno, node in network:
            timeouts = [
                kw.value for kw in node.keywords if kw.arg == "timeout"
            ]
            self.assertEqual(
                len(timeouts), 1,
                f"{relpath}:{lineno} must pass an explicit timeout",
            )
            value = timeouts[0]
            self.assertIsInstance(
                value, ast.Name, f"{relpath}:{lineno}: timeout must be "
                "_NET_TIMEOUT, not a literal",
            )
            self.assertEqual(
                value.id, "_NET_TIMEOUT",
                f"{relpath}:{lineno} must use the shared _NET_TIMEOUT",
            )

    def test_local_reset_sites_keep_the_default(self):
        local = [s for s in self.sites if not _is_network_call(s[2])]
        self.assertTrue(local, "expected local reset GitWorker sites")
        for relpath, lineno, node in local:
            self.assertNotIn(
                "timeout", {kw.arg for kw in node.keywords},
                f"{relpath}:{lineno}: local commands keep the 30s default",
            )


if __name__ == "__main__":
    unittest.main()
