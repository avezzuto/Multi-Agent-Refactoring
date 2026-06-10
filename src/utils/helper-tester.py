def build_refactoring_str(refactorings: list[dict[str, str]]) -> str:
    lines = []
    for i, r in enumerate(refactorings, 1):
        lines.append(f"{i}. `{r['old_name']}` → `{r['new_name']}`")
    return "\n".join(lines)

def main():
    d1= dict()
    d1['old_name'] = 'bernard'
    d1['new_name'] = 'alexander'

    d2 = dict()
    d2['old_name'] = 'derek'
    d2['new_name'] = 'chase'
    res = build_refactoring_str([d1, d2])
    print(res)


if __name__ == '__main__':
    main()