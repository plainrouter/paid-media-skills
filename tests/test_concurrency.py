"""Evaluate the checked-in GitHub expressions with representative event contexts."""
import ast
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def evaluate(expression, context):
    expression = expression.replace('&&', ' and ').replace('||', ' or ')
    tree = ast.parse(expression, mode='eval')
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq, ast.NotEq,
               ast.Call, ast.Name, ast.Attribute, ast.Load, ast.Constant)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError('Unsupported workflow expression')
        if isinstance(node, ast.Name) and node.id not in {'github', 'format'}:
            raise ValueError('Unexpected context')
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id == 'format'):
            raise ValueError('Unexpected function')
    return eval(compile(tree, '<workflow expression>', 'eval'),
                {'__builtins__': {}, 'github': context, 'format': lambda template, *args: template.format(*args)})


def settings(event, run, number=None, head='', ref='main'):
    context = SimpleNamespace(workflow='Validate skills', event_name=event, run_id=run,
                              ref_name=ref, head_ref=head,
                              event=SimpleNamespace(pull_request=SimpleNamespace(number=number)))
    workflow = (ROOT / '.github/workflows/validate.yml').read_text()
    block = workflow.split('concurrency:\n', 1)[1].split('permissions:', 1)[0]
    group = re.search(r'^  group: (.+)$', block, re.M)[1]
    key = re.sub(r'\$\{\{(.*?)\}\}', lambda match: str(evaluate(match[1].strip(), context)), group)
    cancel = re.fullmatch(r'  cancel-in-progress: \$\{\{(.*?)\}\}', block.splitlines()[1])[1]
    return key, evaluate(cancel.strip(), context)


class ConcurrencyTest(unittest.TestCase):
    def test_main_pr_and_fork_main_are_isolated(self):
        main = settings('push', 101)
        later_main = settings('push', 102)
        pr = settings('pull_request', 103, 3, 'codex/skills-repo-3')
        superseded_pr = settings('pull_request', 104, 3, 'codex/skills-repo-3')
        fork_main = settings('pull_request', 105, 4, 'main')
        other_pr = settings('pull_request', 106, 5, 'codex/skills-repo-3')
        dispatch_main = settings('workflow_dispatch', 107)
        self.assertFalse(main[1])
        self.assertFalse(later_main[1])
        self.assertFalse(dispatch_main[1])
        self.assertNotEqual(main[0], later_main[0])
        self.assertEqual(pr, superseded_pr)
        self.assertTrue(pr[1])
        self.assertTrue(fork_main[1])
        self.assertEqual(6, len({main[0], later_main[0], pr[0], fork_main[0], other_pr[0], dispatch_main[0]}))
        for label, result in [('main', main), ('later main', later_main), ('PR #3', pr),
                              ('fork branch main, PR #4', fork_main), ('dispatch main', dispatch_main)]:
            print(f'{label}: group={result[0]}, cancel-in-progress={str(result[1]).lower()}')

    def test_branch_runs_cancel_only_their_own_group(self):
        branch = settings('push', 201, ref='topic')
        superseded = settings('push', 202, ref='topic')
        other = settings('push', 203, ref='another')
        main = settings('push', 204)
        self.assertEqual(branch, superseded)
        self.assertTrue(branch[1])
        self.assertTrue(other[1])
        self.assertNotEqual(branch[0], other[0])
        self.assertNotEqual(branch[0], main[0])
        self.assertFalse(main[1])


if __name__ == '__main__':
    unittest.main()
