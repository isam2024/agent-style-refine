import { useState } from 'react'
import { StyleProfile } from '../types'

interface StyleProfileViewProps {
  profile: StyleProfile
}

function StyleProfileView({ profile }: StyleProfileViewProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-slate-700">Style Profile</h3>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-blue-600 hover:text-blue-700"
        >
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      <h4 className="font-medium text-slate-800 mb-2">{profile.style_name}</h4>

      {/* Original Subject */}
      {profile.original_subject && (
        <div className="mb-3 p-2 bg-slate-50 rounded-lg">
          <p className="text-xs text-slate-500 uppercase mb-1">Original Subject</p>
          <p className="text-sm text-slate-700">{profile.original_subject}</p>
        </div>
      )}

      {/* Core Invariants */}
      <div className="mb-3">
        <p className="text-xs text-slate-500 uppercase mb-1">Core Invariants</p>
        <ul className="text-sm text-slate-600 space-y-1">
          {profile.core_invariants.map((inv, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="text-blue-500 mt-1">•</span>
              <span>{inv}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Palette Preview */}
      <div className="mb-3">
        <p className="text-xs text-slate-500 uppercase mb-1">Palette</p>
        <div className="flex gap-1 mb-2">
          {profile.palette.dominant_colors.map((color, i) => (
            <div
              key={i}
              className="w-8 h-8 rounded border border-slate-200"
              style={{ backgroundColor: color }}
              title={`${color}${profile.palette.color_descriptions?.[i] ? ` - ${profile.palette.color_descriptions[i]}` : ''}`}
            />
          ))}
          <div className="w-px bg-slate-200 mx-1" />
          {profile.palette.accents.map((color, i) => (
            <div
              key={i}
              className="w-6 h-6 rounded border border-slate-200"
              style={{ backgroundColor: color }}
              title={color}
            />
          ))}
        </div>
        {profile.palette.color_descriptions && profile.palette.color_descriptions.length > 0 && (
          <p className="text-xs text-slate-500">
            {profile.palette.color_descriptions.join(', ')}
          </p>
        )}
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="space-y-3 pt-3 border-t border-slate-100">
          {/* Line & Shape */}
          <div>
            <p className="text-xs text-slate-500 uppercase mb-1">Line & Shape</p>
            <p className="text-sm text-slate-600">{profile.line_and_shape.line_quality}</p>
            <p className="text-sm text-slate-600">{profile.line_and_shape.shape_language}</p>
          </div>

          {/* Texture */}
          <div>
            <p className="text-xs text-slate-500 uppercase mb-1">Texture</p>
            <p className="text-sm text-slate-600">{profile.texture.surface}</p>
            {profile.texture.special_effects.length > 0 && (
              <p className="text-sm text-slate-500">
                Effects: {profile.texture.special_effects.join(', ')}
              </p>
            )}
          </div>

          {/* Lighting */}
          <div>
            <p className="text-xs text-slate-500 uppercase mb-1">Lighting</p>
            <p className="text-sm text-slate-600">{profile.lighting.lighting_type}</p>
            <p className="text-sm text-slate-500">
              Shadows: {profile.lighting.shadows}
            </p>
          </div>

          {/* Composition */}
          <div>
            <p className="text-xs text-slate-500 uppercase mb-1">Composition</p>
            <p className="text-sm text-slate-600">{profile.composition.camera}</p>
            <p className="text-sm text-slate-500">{profile.composition.framing}</p>
          </div>

          {/* Motifs */}
          <div>
            <p className="text-xs text-slate-500 uppercase mb-1">Motifs</p>
            <p className="text-sm text-slate-600">
              <span className="text-green-600">Include:</span>{' '}
              {profile.motifs.recurring_elements.join(', ')}
            </p>
            {profile.motifs.forbidden_elements.length > 0 && (
              <p className="text-sm text-slate-600">
                <span className="text-red-600">Avoid:</span>{' '}
                {profile.motifs.forbidden_elements.join(', ')}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default StyleProfileView
