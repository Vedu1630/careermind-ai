import { Suspense, lazy } from 'react'

const ReactDiffViewer = lazy(() =>
  import('react-diff-viewer-continued').then((m) => ({ default: m.default || m }))
)

export default function DiffViewer({ oldValue = '', newValue = '', splitView = true }) {
  if (!oldValue && !newValue) {
    return (
      <div className="p-8 text-center text-[#888] text-sm">
        No diff to display yet. Rewrite a resume to see changes.
      </div>
    )
  }

  return (
    <Suspense
      fallback={
        <div className="p-8 text-center text-[#888] text-sm animate-pulse">
          Loading diff viewer...
        </div>
      }
    >
      <div className="rounded-xl overflow-hidden text-xs" style={{ fontFamily: "'Inter', sans-serif" }}>
        <ReactDiffViewer
          oldValue={oldValue}
          newValue={newValue}
          splitView={splitView}
          useDarkTheme={false}
          leftTitle="Original Resume"
          rightTitle="Rewritten for Role"
          styles={{
            variables: {
              light: {
                diffViewerBackground: '#FFFFFF',
                diffViewerColor: '#111111',
                addedBackground: '#F0FDF4',
                addedColor: '#16A34A',
                removedBackground: '#FEF2F2',
                removedColor: '#DC2626',
                wordAddedBackground: '#DCFCE7',
                wordRemovedBackground: '#FEE2E2',
                addedGutterBackground: '#F0FDF4',
                removedGutterBackground: '#FEF2F2',
                gutterBackground: '#FAFAFA',
                gutterBackgroundDark: '#F0EEFF',
                highlightBackground: 'rgba(107, 92, 231, 0.08)',
                highlightGutterBackground: 'rgba(107, 92, 231, 0.12)',
                codeFoldGutterBackground: '#F0EEFF',
                codeFoldBackground: '#F0EEFF',
                emptyLineBackground: '#FAFAFA',
                gutterColor: '#888888',
                addedGutterColor: '#16A34A',
                removedGutterColor: '#DC2626',
                codeFoldContentColor: '#888888',
                diffViewerTitleBackground: '#F0EEFF',
                diffViewerTitleColor: '#555555',
                diffViewerTitleBorderColor: '#E8E4FF',
              },
            },
          }}
        />
      </div>
    </Suspense>
  )
}
