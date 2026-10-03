using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

#if OWNER_APP
[assembly: AssemblyTitle("AlgoFortis Owner")]
[assembly: AssemblyDescription("AlgoFortis Owner — Trading Research & Risk OS")]
[assembly: AssemblyCompany("AlgoFortis")]
[assembly: AssemblyProduct("AlgoFortis Owner")]
#elif USER_APP
[assembly: AssemblyTitle("AlgoFortis User")]
[assembly: AssemblyDescription("AlgoFortis User — Trading Research & Risk OS")]
[assembly: AssemblyCompany("AlgoFortis")]
[assembly: AssemblyProduct("AlgoFortis User")]
#else
[assembly: AssemblyTitle("AlgoFortis")]
[assembly: AssemblyDescription("AlgoFortis Trading Research & Risk OS")]
[assembly: AssemblyCompany("AlgoFortis")]
[assembly: AssemblyProduct("AlgoFortis")]
#endif
[assembly: AssemblyCopyright("Copyright (C) 2026 AlgoFortis")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace AlgoFortis
{
    public class MainWindow : Form
    {
        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool SetForegroundWindow(IntPtr hWnd);

        [DllImport("user32.dll", EntryPoint = "FindWindow", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

        private static Mutex appMutex;

#if OWNER_APP
        private const string AppRole = "owner";
        private const string AppDisplayName = "AlgoFortis Owner";
        private const string AppWindowTitle = "AlgoFortis Owner - Trading Research & Risk OS";
        private const string AppMutexName = "Global\\AlgoFortis_Owner_App_Instance_Mutex";
        private const string OtherAppMutexName = "Global\\AlgoFortis_User_App_Instance_Mutex";
        private const string WebViewProfileName = "AlgoFortisOwner_WebView2";
#elif USER_APP
        private const string AppRole = "user";
        private const string AppDisplayName = "AlgoFortis User";
        private const string AppWindowTitle = "AlgoFortis User - Trading Research & Risk OS";
        private const string AppMutexName = "Global\\AlgoFortis_User_App_Instance_Mutex";
        private const string OtherAppMutexName = "Global\\AlgoFortis_Owner_App_Instance_Mutex";
        private const string WebViewProfileName = "AlgoFortisUser_WebView2";
#else
        private const string AppRole = "";
        private const string AppDisplayName = "AlgoFortis";
        private const string AppWindowTitle = "AlgoFortis - Trading Research & Risk OS";
        private const string AppMutexName = "Global\\AlgoFortis_Desktop_App_Instance_Mutex";
        private const string OtherAppMutexName = "";
        private const string WebViewProfileName = "AlgoFortis_WebView2";
#endif

        private string appDir;
        private string pythonExe;
        private string runtimeUrl;

        private Panel loadingPanel;
        private Label statusLabel;
        private Label titleLabel;
        private Label subtitleLabel;
        private PictureBox logoBox;
        private ProgressBar progressBar;
        private Panel errorPanel;
        private Label errorLabel;
        private Button closeButton;
        private Button retryButton;

        private WebView2 webView;

        public MainWindow()
        {
            this.appDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
            this.pythonExe = Path.Combine(appDir, "runtime", "python", "python.exe");

            Log("MainWindow constructor started. appDir=" + appDir);
            InitializeComponents();
            Log("InitializeComponents completed.");
        }

        private void Log(string msg)
        {
            try
            {
                string logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AlgoFortis", "logs");
                Directory.CreateDirectory(logDir);
                File.AppendAllText(Path.Combine(logDir, "launcher.log"), DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + " " + msg + Environment.NewLine);
            }
            catch { }
        }

        private void InitializeComponents()
        {
            this.Text = AppWindowTitle;
            this.Name = "AlgoFortisMainWindow";
            this.Size = new Size(1366, 850);
            this.MinimumSize = new Size(1024, 700);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.BackColor = Color.FromArgb(9, 14, 23); // #090e17
            this.ForeColor = Color.White;

            string icoPath = Path.Combine(appDir, "algofortis.ico");
            if (File.Exists(icoPath))
            {
                try
                {
                    this.Icon = new Icon(icoPath);
                }
                catch { }
            }

            // Loading Panel
            loadingPanel = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.FromArgb(9, 14, 23)
            };

            string logoPath = Path.Combine(appDir, "algofortis_logo.png");
            if (File.Exists(logoPath))
            {
                try
                {
                    logoBox = new PictureBox
                    {
                        Image = Image.FromFile(logoPath),
                        SizeMode = PictureBoxSizeMode.Zoom,
                        Size = new Size(110, 110),
                        BackColor = Color.Transparent
                    };
                    loadingPanel.Controls.Add(logoBox);
                }
                catch { }
            }

            titleLabel = new Label
            {
                Text = "AlgoFortis",
                Font = new Font("Segoe UI", 28, FontStyle.Bold),
                ForeColor = Color.FromArgb(245, 158, 11), // Metallic Gold / Amber
                AutoSize = true,
                TextAlign = ContentAlignment.MiddleCenter
            };

            subtitleLabel = new Label
            {
                Text = "Trading Research & Risk OS",
                Font = new Font("Segoe UI", 12, FontStyle.Regular),
                ForeColor = Color.FromArgb(148, 163, 184), // #94a3b8
                AutoSize = true,
                TextAlign = ContentAlignment.MiddleCenter
            };

            statusLabel = new Label
            {
                Text = "Initializing secure runtime environment...",
                Font = new Font("Segoe UI", 10, FontStyle.Italic),
                ForeColor = Color.FromArgb(56, 189, 248), // #38bdf8
                AutoSize = true,
                TextAlign = ContentAlignment.MiddleCenter
            };

            progressBar = new ProgressBar
            {
                Style = ProgressBarStyle.Marquee,
                MarqueeAnimationSpeed = 25,
                Size = new Size(320, 4)
            };

            loadingPanel.Controls.Add(titleLabel);
            loadingPanel.Controls.Add(subtitleLabel);
            loadingPanel.Controls.Add(progressBar);
            loadingPanel.Controls.Add(statusLabel);
            loadingPanel.Resize += (s, e) => LayoutLoading();

            // Error Panel
            errorPanel = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.FromArgb(9, 14, 23),
                Visible = false
            };

            Label errHeader = new Label
            {
                Text = "AlgoFortis Runtime Unavailable",
                Font = new Font("Segoe UI", 20, FontStyle.Bold),
                ForeColor = Color.FromArgb(239, 68, 68), // #ef4444
                AutoSize = true
            };

            errorLabel = new Label
            {
                Text = "",
                Font = new Font("Segoe UI", 10, FontStyle.Regular),
                ForeColor = Color.FromArgb(226, 232, 240),
                AutoSize = false,
                Size = new Size(600, 160)
            };

            closeButton = new Button
            {
                Text = "Exit",
                Size = new Size(100, 32),
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.FromArgb(30, 41, 59),
                ForeColor = Color.White
            };
            closeButton.Click += (s, e) => this.Close();

            retryButton = new Button
            {
                Text = "Retry",
                Size = new Size(100, 32),
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.FromArgb(14, 165, 233),
                ForeColor = Color.White
            };
            retryButton.Click += (s, e) => {
                errorPanel.Visible = false;
                loadingPanel.Visible = true;
                StartAndInitializeAsync();
            };

            errorPanel.Controls.Add(errHeader);
            errorPanel.Controls.Add(errorLabel);
            errorPanel.Controls.Add(closeButton);
            errorPanel.Controls.Add(retryButton);

            errorPanel.Resize += (s, e) => {
                int cx = errorPanel.ClientSize.Width / 2;
                int cy = errorPanel.ClientSize.Height / 2;
                errHeader.Location = new Point(cx - errHeader.Width / 2, cy - 140);
                errorLabel.Location = new Point(cx - errorLabel.Width / 2, cy - 80);
                retryButton.Location = new Point(cx - 110, cy + 100);
                closeButton.Location = new Point(cx + 10, cy + 100);
            };

            // WebView2 Control
            webView = new WebView2
            {
                Dock = DockStyle.Fill,
                Visible = false
            };

            this.Controls.Add(loadingPanel);
            this.Controls.Add(errorPanel);
            this.Controls.Add(webView);
            this.FormClosing += MainWindow_FormClosing;
        }

        private void LayoutLoading()
        {
            int cx = loadingPanel.ClientSize.Width / 2;
            int cy = loadingPanel.ClientSize.Height / 2;

            if (logoBox != null)
            {
                logoBox.Location = new Point(cx - logoBox.Width / 2, cy - 170);
                titleLabel.Location = new Point(cx - titleLabel.Width / 2, cy - 50);
            }
            else
            {
                titleLabel.Location = new Point(cx - titleLabel.Width / 2, cy - 90);
            }

            subtitleLabel.Location = new Point(cx - subtitleLabel.Width / 2, cy + 10);
            progressBar.Location = new Point(cx - progressBar.Width / 2, cy + 50);
            statusLabel.Location = new Point(cx - statusLabel.Width / 2, cy + 70);
        }

        protected override async void OnShown(EventArgs e)
        {
            base.OnShown(e);
            Log("OnShown triggered.");
            LayoutLoading();
            await StartAndInitializeAsync();
        }

        private async Task StartAndInitializeAsync()
        {
            try
            {
                Log("StartAndInitializeAsync started.");
                statusLabel.Text = "Verifying packaged Python environment...";
                if (!File.Exists(pythonExe))
                {
                    Log("pythonExe not found: " + pythonExe);
                    ShowError("AlgoFortis packaged Python runtime is missing.\nExpected path:\n" + pythonExe);
                    return;
                }

                statusLabel.Text = "Starting AlgoFortis runtime...";
                string url = await Task.Run(() => EnsureBackendStarted());
                Log("EnsureBackendStarted returned url: " + url);
                if (string.IsNullOrEmpty(url))
                {
                    ShowError("Backend startup timed out or failed to report a valid loopback origin.\nPlease inspect the backend log under %LOCALAPPDATA%\\AlgoFortis\\logs.");
                    return;
                }

                this.runtimeUrl = url;
                statusLabel.Text = "Initializing embedded browser shell...";

                // WebView2 user data folder in %LOCALAPPDATA%\AlgoFortis_WebView2
                // Keep separated from %LOCALAPPDATA%\AlgoFortis so Chromium sandbox ACEs don't conflict with backend CurrentUserAcl
                string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string webViewCache = Path.Combine(localAppData, WebViewProfileName);
                Directory.CreateDirectory(webViewCache);
                Log("WebView2 user data folder: " + webViewCache);

                var env = await CoreWebView2Environment.CreateAsync(null, webViewCache, null);
                Log("CoreWebView2Environment created.");
                await webView.EnsureCoreWebView2Async(env);
                Log("EnsureCoreWebView2Async completed.");

                // Security hardening
                webView.CoreWebView2.Settings.AreDevToolsEnabled = false;
                webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
                webView.CoreWebView2.Settings.IsStatusBarEnabled = false;
                webView.CoreWebView2.Settings.AreHostObjectsAllowed = false;
                webView.CoreWebView2.Settings.IsWebMessageEnabled = false;

                // Restrict navigation strictly to authoritative runtime loopback origin
                webView.CoreWebView2.NavigationStarting += (s, args) =>
                {
                    Log("NavigationStarting: " + args.Uri);
                    if (!args.Uri.StartsWith(this.runtimeUrl, StringComparison.OrdinalIgnoreCase))
                    {
                        Log("Blocked external navigation to: " + args.Uri);
                        args.Cancel = true;
                    }
                };

                // Block popups and uncontrolled new windows
                webView.CoreWebView2.NewWindowRequested += (s, args) =>
                {
                    Log("NewWindowRequested blocked for: " + args.Uri);
                    args.Handled = true;
                };

                webView.CoreWebView2.NavigationCompleted += (s, args) =>
                {
                    Log("NavigationCompleted. IsSuccess=" + args.IsSuccess + ", status=" + args.WebErrorStatus);
                    if (args.IsSuccess)
                    {
                        loadingPanel.Visible = false;
                        webView.Visible = true;
                    }
                    else
                    {
                        ShowError("Failed to render AlgoFortis UI inside the desktop window.\nNavigation error status: " + args.WebErrorStatus);
                    }
                };

                statusLabel.Text = "Loading AlgoFortis interface...";
                Log("Navigating to runtimeUrl: " + this.runtimeUrl);
                webView.CoreWebView2.Navigate(BuildRoleUrl(this.runtimeUrl));
            }
            catch (Exception ex)
            {
                Log("Exception in StartAndInitializeAsync: " + ex.ToString());
                ShowError("Error during application startup:\n" + ex.Message);
            }
        }

        private string EnsureBackendStarted()
        {
            // 1. Check existing status
            string statusJson = RunController("status");
            Log("EnsureBackendStarted: initial status = " + statusJson);
            if (statusJson.Contains("\"state\": \"READY\""))
            {
                return ExtractUrl(statusJson);
            }

            // 2. Start backend
            string startJson = RunController("start");
            Log("EnsureBackendStarted: start result = " + startJson);
            if (startJson.Contains("\"state\": \"READY\""))
            {
                return ExtractUrl(startJson);
            }

            // 3. Poll for readiness up to 25 seconds
            DateTime deadline = DateTime.UtcNow.AddSeconds(25);
            while (DateTime.UtcNow < deadline)
            {
                Thread.Sleep(500);
                string pollJson = RunController("status");
                if (pollJson.Contains("\"state\": \"READY\""))
                {
                    Log("EnsureBackendStarted: poll success = " + pollJson);
                    return ExtractUrl(pollJson);
                }
            }

            Log("EnsureBackendStarted: deadline expired without READY state.");
            return null;
        }

        private string RunController(string action)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = pythonExe,
                    Arguments = string.Format("-m dashboard.runtime.controller {0} --mode LOCAL_PRIVATE --install-root \"{1}\"", action, appDir),
                    WorkingDirectory = appDir,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };

                psi.EnvironmentVariables["PYTHONPATH"] = appDir;
                try
                {
                    string psMod = Environment.GetEnvironmentVariable("PSModulePath");
                    if (!string.IsNullOrEmpty(psMod))
                    {
                        string[] parts = psMod.Split(';');
                        System.Collections.Generic.List<string> cleanParts = new System.Collections.Generic.List<string>();
                        foreach (string p in parts)
                        {
                            if (p.IndexOf("PowerShell\\7", StringComparison.OrdinalIgnoreCase) < 0 &&
                                p.IndexOf("PowerShell/7", StringComparison.OrdinalIgnoreCase) < 0)
                            {
                                cleanParts.Add(p);
                            }
                        }
                        psi.EnvironmentVariables["PSModulePath"] = string.Join(";", cleanParts.ToArray());
                    }
                }
                catch { }

                using (Process proc = Process.Start(psi))
                {
                    string output = proc.StandardOutput.ReadToEnd();
                    string err = proc.StandardError.ReadToEnd();
                    proc.WaitForExit(30000);
                    if (!string.IsNullOrEmpty(err))
                    {
                        Log(string.Format("RunController({0}) stderr: {1}", action, err));
                    }
                    return output != null ? output.Trim() : "";
                }
            }
            catch (Exception ex)
            {
                Log(string.Format("RunController({0}) exception: {1}", action, ex.Message));
                return "";
            }
        }

        private string ExtractUrl(string json)
        {
            Match m = Regex.Match(json, "\"url\":\\s*\"(http://[^\"]+)\"");
            if (m.Success)
            {
                return m.Groups[1].Value;
            }
            return null;
        }

        private string BuildRoleUrl(string baseUrl)
        {
            if (string.IsNullOrEmpty(AppRole)) return baseUrl;
            return baseUrl.TrimEnd('/') + "/?app=" + AppRole + "&surface=secure-entry";
        }

        private bool OtherRoleRunning()
        {
            if (string.IsNullOrEmpty(OtherAppMutexName)) return false;
            try { using (Mutex other = Mutex.OpenExisting(OtherAppMutexName)) { return true; } }
            catch (WaitHandleCannotBeOpenedException) { return false; }
            catch { return false; }
        }

        private void ShowError(string message)
        {
            if (this.InvokeRequired)
            {
                this.Invoke(new Action<string>(ShowError), message);
                return;
            }

            loadingPanel.Visible = false;
            webView.Visible = false;
            errorLabel.Text = message;
            errorPanel.Visible = true;
        }

        private void MainWindow_FormClosing(object sender, FormClosingEventArgs e)
        {
            try
            {
                if (OtherRoleRunning())
                {
                    Log("MainWindow_FormClosing: other role app remains open; shared backend retained.");
                }
                else
                {
                    Log("MainWindow_FormClosing: final role app closing; stopping shared backend.");
                    RunController("stop");
                }
            }
            catch { }
        }

        [STAThread]
        public static void Main(string[] args)
        {
            bool createdNew;
            appMutex = new Mutex(true, AppMutexName, out createdNew);

            if (!createdNew)
            {
                IntPtr hWnd = FindWindow(null, AppWindowTitle);
                if (hWnd == IntPtr.Zero)
                {
                    hWnd = FindWindow(null, AppDisplayName);
                }
                if (hWnd != IntPtr.Zero)
                {
                    SetForegroundWindow(hWnd);
                }
                return;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            try
            {
                Application.Run(new MainWindow());
            }
            finally
            {
                if (appMutex != null)
                {
                    appMutex.ReleaseMutex();
                    appMutex.Close();
                }
            }
        }
    }
}
