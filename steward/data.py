import copy
import csv
import hashlib
import io
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation


class Conflict(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def valid(value, kind):
    value = value.strip()
    if not value:
        return True
    if kind == "text":
        return True
    if kind == "integer":
        return re.fullmatch(r"[+-]?[0-9]+", value) is not None
    if kind == "decimal":
        try:
            return Decimal(value).is_finite()
        except InvalidOperation:
            return False
    if kind == "date":
        try:
            return len(value) == 10 and date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    raise ValueError("Unknown type rule")


class Dataset:
    def __init__(self, headers, rows):
        if not isinstance(headers, list) or not headers or len(headers) > 100 or any(not isinstance(h, str) or not h.strip() for h in headers) or len(set(headers)) != len(headers):
            raise ValueError("Use 1..100 unique nonempty string headers")
        if not isinstance(rows, list) or len(rows) > 10000 or any(not isinstance(row, list) or len(row) != len(headers) or any(not isinstance(cell, str) for cell in row) for row in rows):
            raise ValueError("Use at most 10000 rectangular string rows")
        if sum(len(c.encode()) for row in rows for c in row) > 8*1024*1024:
            raise ValueError("Cell data exceeds 8 MiB")
        self._headers, self._rows = copy.deepcopy(headers), copy.deepcopy(rows)

    @property
    def headers(self):
        return self._headers.copy()

    @property
    def rows(self):
        return copy.deepcopy(self._rows)

    @classmethod
    def from_csv(cls, content):
        if not isinstance(content, str) or len(content.encode()) > 10*1024*1024:
            raise ValueError("CSV input must be text up to 10 MiB")
        rows = list(csv.reader(io.StringIO(content, newline=""), strict=True))
        if not rows:
            raise ValueError("CSV has no header")
        rows[0][0:1] = [rows[0][0].removeprefix("\ufeff")] if rows[0] else []
        return cls(rows[0], rows[1:])

    def snapshot(self):
        return {"headers": self.headers, "rows": self.rows}

    @property
    def fingerprint(self):
        return digest(self.snapshot())

    def duplicates(self, keys=None):
        keys = self.headers if keys is None else keys
        if not isinstance(keys, list) or not keys or len(keys) != len(set(keys)) or any(k not in self._headers for k in keys):
            raise ValueError("Duplicate keys must be distinct existing headers")
        indices = [self._headers.index(k) for k in keys]
        groups = {}
        for index, row in enumerate(self._rows):
            key = tuple(row[i] for i in indices)
            groups.setdefault(key, []).append(index)
        return [group for group in groups.values() if len(group) > 1]

    def profile(self):
        columns = []
        for index, name in enumerate(self._headers):
            values = [row[index] for row in self._rows]
            nonempty = [v for v in values if v.strip()]
            columns.append({"name": name, "missing": len(values)-len(nonempty), "distinct_exact": len(set(values)),
                            "surrounding_whitespace": sum(v != v.strip() for v in values),
                            "compatible_nonempty": {kind: sum(valid(v, kind) for v in nonempty) for kind in ("integer", "decimal", "date")}})
        return {"rows": len(self._rows), "columns": columns, "exact_duplicate_groups": self.duplicates(), "fingerprint": self.fingerprint}

    def check(self, rules):
        if not isinstance(rules, dict) or any(name not in self._headers for name in rules):
            raise ValueError("Rules must reference existing columns")
        issues = []
        for name, rule in rules.items():
            if not isinstance(rule, dict) or set(rule) - {"required", "type", "enum", "min", "max", "unique"}:
                raise ValueError("Unknown quality rule")
            kind = rule.get("type", "text")
            if kind not in ("text", "integer", "decimal", "date") or any(type(rule[k]) is not bool for k in ("required", "unique") if k in rule):
                raise ValueError("Invalid rule type or boolean")
            if "enum" in rule and (not isinstance(rule["enum"], list) or any(not isinstance(v, str) for v in rule["enum"])):
                raise ValueError("Enum must be a list of strings")
            bounds = {}
            for key in ("min", "max"):
                if key in rule:
                    if kind not in ("integer", "decimal") or type(rule[key]) not in (int, float, str):
                        raise ValueError("Numeric bounds require a numeric type")
                    try:
                        bound = Decimal(str(rule[key]))
                    except InvalidOperation as exc:
                        raise ValueError("Invalid numeric bound") from exc
                    if not bound.is_finite():
                        raise ValueError("Bounds must be finite")
                    bounds[key] = bound
            if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
                raise ValueError("Reversed numeric bounds")
            col = self._headers.index(name)
            seen = {}
            for index, row in enumerate(self._rows):
                raw, value = row[col], row[col].strip()
                codes = []
                if not value:
                    if rule.get("required"):
                        codes.append("missing")
                else:
                    if not valid(raw, kind):
                        codes.append("type")
                    elif kind in ("integer", "decimal"):
                        number = Decimal(value)
                        if "min" in bounds and number < bounds["min"]:
                            codes.append("below_min")
                        if "max" in bounds and number > bounds["max"]:
                            codes.append("above_max")
                    if "enum" in rule and value not in rule["enum"]:
                        codes.append("enum")
                    if rule.get("unique"):
                        if value in seen:
                            codes.append("duplicate")
                        seen[value] = index
                for code in codes:
                    issues.append({"row": index, "column": name, "code": code, "value": raw})
        return issues

    def propose(self, *, trim=None, missing=None, drop_duplicates=False):
        trim, missing = [] if trim is None else trim, {} if missing is None else missing
        if not isinstance(trim, list) or len(trim) != len(set(trim)) or any(name not in self._headers for name in trim) or not isinstance(missing, dict) or any(name not in self._headers or not isinstance(value, str) for name, value in missing.items()) or type(drop_duplicates) is not bool:
            raise ValueError("Invalid cleaning proposal")
        rows, changes = self.rows, []
        for index, row in enumerate(rows):
            for col, name in enumerate(self._headers):
                before = row[col]
                value = before.strip() if name in trim else before
                reasons = ["trim"] if value != before else []
                if not value.strip() and name in missing:
                    value = missing[name]
                    reasons.append("fill_missing")
                if value != before:
                    row[col] = value
                    changes.append({"row": index, "column": name, "before": before, "after": value, "reasons": reasons})
        removed, seen = [], set()
        if drop_duplicates:
            for index, row in enumerate(rows):
                key = tuple(row)
                if key in seen:
                    removed.append(index)
                seen.add(key)
        clean = Dataset(self.headers, [row for i, row in enumerate(rows) if i not in set(removed)])
        return {"version": 1, "source": self.fingerprint, "target": clean.fingerprint,
                "options": {"trim": trim.copy(), "missing": missing.copy(), "drop_duplicates": drop_duplicates},
                "changes": changes, "removed_rows": removed,
                "original": self.snapshot(), "cleaned": clean.snapshot()}

    def apply(self, proposal):
        if not isinstance(proposal, dict) or proposal.get("source") != self.fingerprint or proposal.get("version") != 1:
            raise Conflict("Proposal does not match current dataset")
        try:
            expected = self.propose(**proposal["options"])
        except (KeyError, TypeError, ValueError) as exc:
            raise Conflict("Invalid proposal options") from exc
        if expected != proposal:
            raise Conflict("Proposal contents changed; regenerate for review")
        return Dataset(**proposal["cleaned"])

    def undo(self, proposal):
        if not isinstance(proposal, dict) or proposal.get("target") != self.fingerprint:
            raise Conflict("Current data does not match proposal output")
        try:
            original = Dataset(**proposal["original"])
            if original.propose(**proposal["options"]) != proposal:
                raise Conflict("Proposal contents changed")
        except (KeyError, TypeError, ValueError) as exc:
            raise Conflict("Invalid rollback proposal") from exc
        return original

    def to_csv(self, *, spreadsheet_safe=False):
        if type(spreadsheet_safe) is not bool:
            raise ValueError("spreadsheet_safe must be boolean")
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        for row in [self.headers, *self.rows]:
            writer.writerow(["'"+v if spreadsheet_safe and (v.lstrip().startswith(("=", "+", "-", "@")) or v.startswith(("\t", "\r", "\n"))) else v for v in row])
        return output.getvalue()
