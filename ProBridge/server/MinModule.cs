using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using ArcGIS.Desktop.Framework.Contracts;

namespace ProBridge
{
    internal class ProBridgeModule : Module
    {
        private static readonly string LogPath = Path.Combine(Path.GetTempPath(), "probridge_init.log");

        private static void Log(string message)
        {
            try
            {
                File.AppendAllText(LogPath, DateTime.Now.ToString("HH:mm:ss") + " " + message + Environment.NewLine);
            }
            catch
            {
            }
        }

        static ProBridgeModule()
        {
            Log("static ctor");
        }

        protected override bool Initialize()
        {
            Log("Initialize");
            try
            {
                var listener = new TcpListener(IPAddress.Loopback, 7789);
                listener.Start();
                Log("port 7789 listening");
            }
            catch (Exception ex)
            {
                Log("bind failed: " + ex.Message);
            }
            return true;
        }

        protected override void Uninitialize()
        {
            Log("Uninitialize");
        }
    }
}
