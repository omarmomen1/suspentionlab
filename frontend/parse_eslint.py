import json
r = json.load(open('eslint_report.json', encoding='utf-8-sig'))
for f in r:
    if f['messages']:
        print(f"{f['filePath'].split('frontend')[1]}:")
        for m in f['messages']:
            print(f"  {m['line']}: {m['ruleId']} ({m['severity']})")
