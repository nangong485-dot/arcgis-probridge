using System;
using System.Windows.Threading;
using ArcGIS.Desktop.Core.Events;
using ArcGIS.Desktop.Framework.Contracts;

namespace ProBridge
{
    internal class ProBridgeModule : Module
    {
        private BridgeServer _server;

        protected override bool Initialize()
        {
            _server = new BridgeServer(7788);
            _server.Start();

            // The pane is opened on demand (Add-In tab button, or the show_agent
            // command) rather than at startup: if WebView2 fails to initialise it
            // takes Pro down with it, and that must not happen on every launch.
            ProjectOpenedEvent.Subscribe(OnProjectOpened);

            return true;
        }

        private static void OnProjectOpened(ProjectEventArgs args)
        {
            // nothing for now; kept so the pane could be auto-opened later
        }

        protected override void Uninitialize()
        {
            ProjectOpenedEvent.Unsubscribe(OnProjectOpened);
            _server?.Stop();
            _server = null;
        }
    }
}
