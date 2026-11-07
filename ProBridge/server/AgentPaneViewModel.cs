using System;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;

namespace ProBridge
{
    /// <summary>
    /// The dock pane that hosts the agent UI. Its content is AgentPaneView,
    /// wired up through Config.daml.
    /// </summary>
    public class AgentPaneViewModel : DockPane
    {
        private const string DockPaneId = "ProBridge_AgentPane";
        private static AgentWindow _floating;

        public AgentPaneViewModel() { }

        /// <summary>
        /// Puts the agent UI on screen: docked on the right if Pro registered the
        /// pane, otherwise as a floating window. Must be called on the UI thread.
        /// </summary>
        public static object ShowOrWindow()
        {
            DockPane pane = null;
            try
            {
                pane = FrameworkApplication.DockPaneManager.Find(DockPaneId);
            }
            catch
            {
                pane = null;
            }

            if (pane != null)
            {
                pane.Activate();
                return new { mode = "dockpane", visible = pane.IsVisible, caption = pane.Caption };
            }

            if (_floating == null || !_floating.IsLoaded)
            {
                _floating = new AgentWindow();
                _floating.Closed += (s, e) => _floating = null;
                _floating.Show();
            }
            else
            {
                _floating.Activate();
            }

            return new { mode = "window", note = "dock pane not registered by Pro" };
        }

        public static void Show()
        {
            ShowOrWindow();
        }
    }

    public class ShowAgentButton : Button
    {
        protected override void OnClick()
        {
            AgentPaneViewModel.ShowOrWindow();
        }
    }
}
