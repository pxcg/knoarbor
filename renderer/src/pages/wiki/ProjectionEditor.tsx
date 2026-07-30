import type { ProjectionEditorState, ProjectionEntityEdit, ProjectionRelationEdit, ProjectionRelationObjectEdit } from "../../api/client";
import type { ReactNode } from "react";

type Props = {
  edit: ProjectionEditorState;
  error: string | null;
  language: "zh" | "en";
  pending: boolean;
  onCancel: () => void;
  onChange: (edit: ProjectionEditorState) => void;
  onSave: () => void;
};

export function ProjectionEditor({ edit, error, language, pending, onCancel, onChange, onSave }: Props) {
  const zh = language === "zh";
  const entityOptions = relationObjectOptions(edit.entities, edit.relations);
  const canSave = Boolean(
    edit.base_revision_id
      && edit.claims.every((claim) => claim.claim.trim())
      && edit.entities.every((entity) => entity.name.trim())
      && edit.relations.every((relation) => relation.subject.name.trim() && relation.predicate.trim() && relation.object.name.trim() && relation.source_claim_ids.length),
  );

  return (
    <div className="settings-modal-backdrop" onClick={onCancel}>
      <section className="settings-modal projection-editor-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <header className="settings-modal-header">
          <div>
            <h2>{zh ? "编辑知识投影" : "Edit knowledge projection"}</h2>
            <p>{zh ? "只修改知识内容；原文和证据保持只读。" : "Edit knowledge content only. Raw source and evidence stay read-only."}</p>
          </div>
          <button className="icon-button subtle settings-modal-close" type="button" onClick={onCancel}>✕</button>
        </header>
        {error ? <p className="settings-action-note warning projection-editor-error" role="alert">{error}</p> : null}

        <div className="settings-modal-content projection-editor-content">
          <EditorSection title={zh ? "综合说明" : "Synthesis"}>
            <textarea
              className="projection-editor-textarea synthesis"
              value={edit.synthesis}
              onChange={(event) => onChange({ ...edit, synthesis: event.target.value })}
            />
          </EditorSection>

          <EditorSection title={zh ? "核心断言" : "Claims"} note={zh ? "可修改文本；断言身份与证据不可更改。" : "Text is editable; identity and evidence are fixed."}>
            <div className="projection-editor-stack">
              {edit.claims.map((claim, index) => (
                <article className="projection-editor-card" key={claim.id}>
                  <label>
                    <span>{`C${index + 1}`}</span>
                    <textarea
                      className="projection-editor-textarea claim"
                      value={claim.claim}
                      onChange={(event) => onChange({
                        ...edit,
                        claims: edit.claims.map((item) => item.id === claim.id ? { ...item, claim: event.target.value } : item),
                      })}
                    />
                  </label>
                  {claim.evidence.length ? (
                    <details className="projection-editor-evidence">
                      <summary>{zh ? `查看证据（${claim.evidence.length}）` : `View evidence (${claim.evidence.length})`}</summary>
                      {claim.evidence.map((evidence, evidenceIndex) => (
                        <blockquote key={`${claim.id}-${evidence.source_unit_id || evidenceIndex}`}>
                          <p>{evidence.excerpt}</p>
                          <small>{evidence.source_path || evidence.source_unit_id || (zh ? "原始资料" : "Raw source")}</small>
                        </blockquote>
                      ))}
                    </details>
                  ) : null}
                </article>
              ))}
            </div>
          </EditorSection>

          <EditorSection title={zh ? "实体" : "Entities"}>
            <div className="projection-editor-stack">
              {edit.entities.map((entity, index) => (
                <div className="projection-editor-row entity" key={entity.atom_id || `entity-${index}`}>
                  <input
                    aria-label={zh ? "实体名称" : "Entity name"}
                    value={entity.name}
                    onChange={(event) => updateEntity(edit, index, { ...entity, name: event.target.value }, onChange)}
                  />
                  <input
                    aria-label={zh ? "实体别名" : "Entity aliases"}
                    placeholder={zh ? "别名，用逗号分隔" : "Aliases, comma separated"}
                    value={entity.aliases.join(", ")}
                    onChange={(event) => updateEntity(edit, index, { ...entity, aliases: commaList(event.target.value) }, onChange)}
                  />
                  <button className="icon-button subtle" type="button" aria-label={zh ? "删除实体" : "Remove entity"} onClick={() => onChange({ ...edit, entities: edit.entities.filter((_item, itemIndex) => itemIndex !== index) })}>✕</button>
                </div>
              ))}
              <button className="button secondary projection-editor-add" type="button" onClick={() => onChange({ ...edit, entities: [...edit.entities, { name: "", aliases: [] }] })}>
                {zh ? "添加实体" : "Add entity"}
              </button>
            </div>
          </EditorSection>

          <EditorSection title={zh ? "关系" : "Relations"} note={zh ? "每条关系必须关联至少一个已有断言。" : "Every relation must reference at least one existing claim."}>
            <div className="projection-editor-stack">
              {edit.relations.map((relation, index) => (
                <article className="projection-editor-card relation" key={relation.id || `relation-${index}`}>
                  <div className="projection-editor-row relation-main">
                    <RelationObjectSelect
                      label={zh ? "主语" : "Subject"}
                      options={entityOptions}
                      value={relation.subject}
                      onChange={(value) => updateRelation(edit, index, { ...relation, subject: value }, onChange)}
                    />
                    <label>
                      <span>{zh ? "关系" : "Predicate"}</span>
                      <input
                        value={relation.predicate}
                        onChange={(event) => updateRelation(edit, index, { ...relation, predicate: event.target.value }, onChange)}
                      />
                    </label>
                    <RelationObjectSelect
                      label={zh ? "宾语" : "Object"}
                      options={entityOptions}
                      value={relation.object}
                      onChange={(value) => updateRelation(edit, index, { ...relation, object: value }, onChange)}
                    />
                    <button className="icon-button subtle" type="button" aria-label={zh ? "删除关系" : "Remove relation"} onClick={() => onChange({ ...edit, relations: edit.relations.filter((_item, itemIndex) => itemIndex !== index) })}>✕</button>
                  </div>
                  <div className="projection-editor-claims-select">
                    <span>{zh ? "支持断言" : "Supporting claims"}</span>
                    <span className="projection-editor-claim-options">
                      {edit.claims.map((claim, claimIndex) => (
                        <label key={claim.id}>
                          <input
                            type="checkbox"
                            checked={relation.source_claim_ids.includes(claim.id)}
                            onChange={(event) => updateRelation(edit, index, {
                              ...relation,
                              source_claim_ids: event.target.checked
                                ? [...relation.source_claim_ids, claim.id]
                                : relation.source_claim_ids.filter((claimId) => claimId !== claim.id),
                            }, onChange)}
                          />
                          <strong>{`C${claimIndex + 1}`}</strong>
                          <span>{claim.claim}</span>
                        </label>
                      ))}
                    </span>
                  </div>
                </article>
              ))}
              <button
                className="button secondary projection-editor-add"
                type="button"
                disabled={!edit.entities.length || !edit.claims.length}
                onClick={() => {
                  const first = edit.entities[0];
                  const object = { atom_id: first.atom_id, name: first.name };
                  onChange({
                    ...edit,
                    relations: [...edit.relations, { subject: object, predicate: "", object, source_claim_ids: [edit.claims[0].id] }],
                  });
                }}
              >
                {zh ? "添加关系" : "Add relation"}
              </button>
            </div>
          </EditorSection>
        </div>

        <div className="wiki-edit-actions">
          <button className="button secondary" type="button" onClick={onCancel}>{zh ? "取消" : "Cancel"}</button>
          <button className="button primary" type="button" disabled={pending || !canSave} onClick={onSave}>
            {pending ? (zh ? "正在保存…" : "Saving…") : (zh ? "保存" : "Save")}
          </button>
        </div>
      </section>
    </div>
  );
}

function EditorSection({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="projection-editor-section">
      <header><h3>{title}</h3>{note ? <p>{note}</p> : null}</header>
      {children}
    </section>
  );
}

function RelationObjectSelect({ label, options, value, onChange }: {
  label: string;
  options: ProjectionRelationObjectEdit[];
  value: ProjectionRelationObjectEdit;
  onChange: (value: ProjectionRelationObjectEdit) => void;
}) {
  const identity = objectIdentity(value);
  return (
    <label>
      <span>{label}</span>
      <select value={identity} onChange={(event) => onChange(options.find((option) => objectIdentity(option) === event.target.value) || value)}>
        {options.map((option) => <option key={objectIdentity(option)} value={objectIdentity(option)}>{option.name}</option>)}
      </select>
    </label>
  );
}

function updateEntity(edit: ProjectionEditorState, index: number, entity: ProjectionEntityEdit, onChange: Props["onChange"]) {
  onChange({ ...edit, entities: edit.entities.map((item, itemIndex) => itemIndex === index ? entity : item) });
}

function updateRelation(edit: ProjectionEditorState, index: number, relation: ProjectionRelationEdit, onChange: Props["onChange"]) {
  onChange({ ...edit, relations: edit.relations.map((item, itemIndex) => itemIndex === index ? relation : item) });
}

function relationObjectOptions(entities: ProjectionEntityEdit[], relations: ProjectionRelationEdit[]) {
  const options = [
    ...entities.map((entity) => ({ atom_id: entity.atom_id, name: entity.name })),
    ...relations.flatMap((relation) => [relation.subject, relation.object]),
  ];
  const seen = new Set<string>();
  return options.filter((option) => {
    const identity = objectIdentity(option);
    if (!option.name || seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });
}

function objectIdentity(value: ProjectionRelationObjectEdit) {
  return value.atom_id || `name:${value.name.toLocaleLowerCase()}`;
}

function commaList(value: string) {
  return value.split(/[,，]/).map((item) => item.trim()).filter(Boolean);
}

