export const choiceKey = (value: string) => value.trim().toLowerCase();

export const matchingChoice = (value: string, options: string[]) => options.find(option => choiceKey(option) === choiceKey(value));

export function uniqueChoices(options: string[]) {
  const seen = new Set<string>();
  return options.filter(option => {
    const key = choiceKey(option);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
