/**
 * SourceTypeLabel: Consistent presentation of document source types.
 * ContentLevelLabel: Human-readable presentation of content depth level.
 *
 * Maps backend enum values to human-readable labels and icons.
 * Degrades safely for unknown future values.
 */
import React from 'react';
import { FileUp, Globe, Link2, BookOpen, Database } from 'lucide-react';
import { SourceType, ContentLevel } from '../../types/document';

// ─── SourceTypeLabel ─────────────────────────────────────────────────────────

interface SourceTypeLabelProps {
  sourceType: SourceType | string;
}

const SOURCE_TYPE_CONFIG: Record<
  string,
  { label: string; icon: React.ElementType }
> = {
  uploaded_file: { label: 'Uploaded File', icon: FileUp },
  web_page: { label: 'Web Page', icon: Globe },
  doi: { label: 'DOI', icon: Link2 },
  openalex: { label: 'OpenAlex', icon: BookOpen },
  crossref: { label: 'Crossref', icon: Database },
};

export const SourceTypeLabel: React.FC<SourceTypeLabelProps> = ({
  sourceType,
}) => {
  const config = SOURCE_TYPE_CONFIG[sourceType] ?? {
    label: String(sourceType).replace(/_/g, ' '),
    icon: Database,
  };
  const Icon = config.icon;

  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-[#929792]">
      <Icon className="w-3 h-3 shrink-0" />
      <span>{config.label}</span>
    </span>
  );
};

// ─── ContentLevelLabel ────────────────────────────────────────────────────────

const CONTENT_LEVEL_LABELS: Record<string, string> = {
  user_document: 'User Document',
  full_text: 'Full Text',
  abstract: 'Abstract',
  metadata_only: 'Metadata Only',
  web_page: 'Web Page',
};

interface ContentLevelLabelProps {
  contentLevel: ContentLevel | string;
}

export const ContentLevelLabel: React.FC<ContentLevelLabelProps> = ({
  contentLevel,
}) => {
  const label =
    CONTENT_LEVEL_LABELS[contentLevel] ??
    String(contentLevel).replace(/_/g, ' ');

  return (
    <span className="text-[10px] text-[#929792]" title="Content coverage level">
      {label}
    </span>
  );
};
