package de.kplager.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.text.InputType;
import android.view.KeyEvent;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.Toast;

/**
 * KP Lager als Android-App: zeigt den Lager-Server in einem WebView.
 * Offline-Lesen und die Offline-Warteschlange kommen vom Service Worker der Web-App.
 */
public class MainActivity extends Activity {
    private static final String PREFS = "kp_lager";
    private static final String KEY_SERVER = "server";
    private static final int REQ_FILE = 1;
    private static final int REQ_CAMERA = 2;

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private Uri cameraUri;
    private PermissionRequest pendingPermission;
    private boolean errorShown = false;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        setContentView(web);
        setup(web);
        String server = server();
        if (server.isEmpty()) {
            askServer(BuildConfig.DEFAULT_SERVER, true);
        } else if (state != null) {
            web.restoreState(state);
        } else {
            web.loadUrl(server);
        }
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private String server() {
        return prefs().getString(KEY_SERVER, "");
    }

    static String normalize(String raw) {
        String s = raw == null ? "" : raw.trim();
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        if (s.isEmpty()) return "";
        if (!s.contains("://")) s = "https://" + s;
        return s;
    }

    private boolean sameServer(Uri uri) {
        Uri base = Uri.parse(server());
        return uri.getHost() != null && uri.getHost().equalsIgnoreCase(base.getHost())
                && uri.getPort() == base.getPort();
    }

    private void setup(WebView view) {
        WebSettings s = view.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setUserAgentString(s.getUserAgentString() + " KPLagerApp/" + BuildConfig.VERSION_NAME);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(view, false);

        view.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                Uri uri = req.getUrl();
                if (sameServer(uri)) return false;
                try {  // fremde Links (Datenblätter, Shops) im Browser
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (ActivityNotFoundException e) {
                    Toast.makeText(MainActivity.this, "Kein Programm für " + uri, Toast.LENGTH_SHORT).show();
                }
                return true;
            }

            @Override
            public void onPageStarted(WebView v, String url, Bitmap icon) {
                errorShown = false;
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {
                // Ohne Netz liefert der Service Worker gespeicherte Seiten; nur wenn auch das scheitert:
                if (req.isForMainFrame() && !errorShown) {
                    errorShown = true;
                    showOfflineDialog(String.valueOf(err.getDescription()));
                }
            }
        });

        view.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                // Kamera für den QR-Scan (/scan)
                runOnUiThread(() -> {
                    if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                        request.grant(request.getResources());
                    } else {
                        pendingPermission = request;
                        requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAMERA);
                    }
                });
            }

            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                // Foto-Upload: Kamera oder Galerie
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent pick = params.createIntent();
                Intent chooser = Intent.createChooser(pick, "Foto wählen");
                cameraUri = null;
                if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    try {  // Zieldatei in der Mediathek (braucht keinen FileProvider)
                        ContentValues values = new ContentValues();
                        values.put(MediaStore.Images.Media.DISPLAY_NAME, "kp-lager-" + System.currentTimeMillis() + ".jpg");
                        values.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                        cameraUri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);
                        Intent shoot = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                        shoot.putExtra(MediaStore.EXTRA_OUTPUT, cameraUri);
                        shoot.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                        chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{shoot});
                    } catch (RuntimeException e) {
                        cameraUri = null;
                    }
                }
                try {
                    startActivityForResult(chooser, REQ_FILE);
                } catch (ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });

        view.setDownloadListener((url, userAgent, disposition, mime, length) -> {
            // XLSX-Etiketten, JSON-Export, Datenblätter
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
            String name = URLUtil.guessFileName(url, disposition, mime);
            r.addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url));
            r.addRequestHeader("User-Agent", userAgent);
            r.setMimeType(mime);
            r.setTitle(name);
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(r);
            Toast.makeText(this, "Download: " + name, Toast.LENGTH_SHORT).show();
        });
    }

    private void showOfflineDialog(String reason) {
        new AlertDialog.Builder(this)
                .setTitle("Lager nicht erreichbar")
                .setMessage(server() + "\n\n" + reason
                        + "\n\nIm WLAN des Lagers? Ist das Zertifikat (ca.crt) installiert?")
                .setPositiveButton("Erneut versuchen", (d, w) -> web.reload())
                .setNeutralButton("Adresse ändern", (d, w) -> askServer(server(), false))
                .setNegativeButton("Schließen", null)
                .show();
    }

    private void askServer(String current, boolean first) {
        EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(current.isEmpty() ? BuildConfig.DEFAULT_SERVER : current);
        input.setSelectAllOnFocus(true);
        AlertDialog.Builder b = new AlertDialog.Builder(this)
                .setTitle("Adresse des Lagers")
                .setMessage("z. B. https://lager.home.lan oder http://192.168.1.5:8000")
                .setView(input)
                .setCancelable(!first)
                .setPositiveButton("Öffnen", (d, w) -> {
                    String url = normalize(input.getText().toString());
                    if (url.isEmpty()) url = BuildConfig.DEFAULT_SERVER;
                    prefs().edit().putString(KEY_SERVER, url).apply();
                    web.clearHistory();
                    web.loadUrl(url);
                });
        if (!first) b.setNegativeButton("Abbrechen", null);
        b.show();
    }

    @Override
    public boolean onKeyLongPress(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {  // langer Druck auf Zurück: Adresse ändern
            askServer(server(), false);
            return true;
        }
        return super.onKeyLongPress(keyCode, event);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) event.startTracking();
        return super.onKeyDown(keyCode, event);
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        if (code == REQ_CAMERA && pendingPermission != null) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
                pendingPermission.grant(pendingPermission.getResources());
            } else {
                pendingPermission.deny();
            }
            pendingPermission = null;
        }
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        if (code == REQ_FILE && fileCallback != null) {
            Uri[] picked = WebChromeClient.FileChooserParams.parseResult(result, data);
            if (picked == null && result == RESULT_OK && cameraUri != null) {
                picked = new Uri[]{cameraUri};  // Foto mit der Kamera aufgenommen
            } else if (cameraUri != null && (picked == null || result != RESULT_OK)) {
                getContentResolver().delete(cameraUri, null, null);  // leere Zieldatei aufräumen
            }
            fileCallback.onReceiveValue(picked);
            fileCallback = null;
            cameraUri = null;
            return;
        }
        super.onActivityResult(code, result, data);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }
}
