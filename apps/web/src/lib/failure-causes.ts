type LabelledCause = { display_name_es: string; category_name_es?: string | null; group_name_es?: string | null };

/** "Grupo · Categoría · Causa": causes with the same name differ by category and group. */
export function failureCauseLabel(cause: LabelledCause): string {
  return [cause.group_name_es, cause.category_name_es, cause.display_name_es].filter(Boolean).join(" · ");
}
