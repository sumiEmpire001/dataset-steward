import json
from steward import Dataset

data = Dataset.from_csv('name,age,group\n Ada ,12,A\nAda,12,A\nBo,,B\n')
print(json.dumps(data.profile(), indent=2))
proposal = data.propose(trim=["name"], missing={"age": "unknown"}, drop_duplicates=True)
cleaned = data.apply(proposal)
print("Reviewed synthetic transformation:", json.dumps(proposal["changes"]))
print(cleaned.to_csv())
assert cleaned.undo(proposal).snapshot() == data.snapshot()
print("Rollback restored every original cell and row")
