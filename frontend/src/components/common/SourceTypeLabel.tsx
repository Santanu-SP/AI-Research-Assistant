import React from 'react';
import {
  FileUp,
  Globe,
  Link2,
  BookOpen,
  Database,
  Video,
  Music,
  Image,
} from 'lucide-react';
import { SourceType, ContentLevel } from '../../types/document';


interface SourceTypeLabelProps {
  sourceType: SourceType | string;
}

const SOURCE_TYPE_CONFIG: Record<
  string,
  { label: string; icon: React.ElementType }
> = {
  uploaded_file: { label: 'Uploaded file', icon: FileUp },
  web_page: { label: 'Web page', icon: Globe },
  web: { label: 'Website', icon: Globe },
  wikipedia: { label: 'Wikipedia', icon: Globe },
  youtube_video: { label: 'YouTube video', icon: Video },
  audio_file: { label: 'Audio', icon: Music },
  video_file: { label: 'Video', icon: Video },
  image_file: { label: 'Image', icon: Image },
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
    <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
      <Icon className="w-3 h-3 shrink-0" />
      <span>{config.label}</span>
    </span>
  );
};


const CONTENT_LEVEL_LABELS: Record<string, string> = {
  user_document: 'Your document',
  full_text: 'Full text',
  abstract: 'Abstract only',
  metadata_only: 'Metadata only',
  web_page: 'Web page',
  transcript: 'Transcript',
  visual_analysis: 'Visual analysis',
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
    <span className="text-xs text-ink-muted" title="Content coverage level">
      {label}
    </span>
  );
};
