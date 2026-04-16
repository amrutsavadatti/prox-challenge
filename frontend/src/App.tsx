import { useStore } from '@/store';
import { Sidebar } from '@/components/Sidebar';
import { ChatPanel } from '@/components/ChatPanel';
import { ArtifactPanel } from '@/components/ArtifactPanel';
import { TooltipProvider } from '@/components/ui/tooltip';

function App() {
  const { sidebarOpen, artifactPanelOpen } = useStore();

  return (
    <TooltipProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
        {/* Left Sidebar */}
        <div
          className={`shrink-0 border-r border-border transition-all duration-300 ease-in-out overflow-hidden ${
            sidebarOpen ? 'w-64' : 'w-0'
          }`}
        >
          <div className="w-64 h-full">
            <Sidebar />
          </div>
        </div>

        {/* Center Chat Panel */}
        <div className="flex-1 min-w-0">
          <ChatPanel />
        </div>

        {/* Right Artifact Panel */}
        <div
          className={`shrink-0 transition-all duration-300 ease-in-out overflow-hidden ${
            artifactPanelOpen ? 'w-[45%] max-w-[700px]' : 'w-0'
          }`}
        >
          <div className="w-[700px] max-w-[45vw] h-full">
            <ArtifactPanel />
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}

export default App;
