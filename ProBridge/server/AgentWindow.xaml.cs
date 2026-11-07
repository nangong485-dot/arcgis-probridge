using System;
using System.Windows;

namespace ProBridge
{
    /// <summary>
    /// Floating fallback for the agent UI. If Pro refuses to register the dock pane
    /// (Config.daml is loaded but the pane never appears), this still puts the
    /// window on screen — it hosts the same AgentPaneView.
    /// </summary>
    public partial class AgentWindow : Window
    {
        public AgentWindow()
        {
            InitializeComponent();
            Title = "ProBridge Agent";
        }
    }
}
