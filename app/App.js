import { useState, useRef, useEffect } from 'react';
import {
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Switch,
  Alert,
  Linking,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';

// Same-origin by default: app.py serves this web build AND the /ask API
// from one Flask process, so the web version needs no configured host at
// all. Only the native (Android/iOS) build - which runs on-device, with no
// "origin" of its own - needs a real absolute URL here.
const BACKEND_URL = Platform.OS === 'web' ? '' : 'https://apprentice.koroai.org';

const DISCLAIMER =
  "I'm the Tohunga's Apprentice, not a tohunga myself - I carry real, sourced " +
  'research about tikanga and tohunga traditions, but real authority over tapu ' +
  'matters belongs to your own kaumātua, hapū, and iwi. Tikanga genuinely differs ' +
  'by iwi and marae - treat what I say as a starting point, not the final word.';

// Real, working direct-download link for the Android build (see
// README.md - built via EAS, hosted by Expo, verified publicly
// reachable). Only shown on web, and only worth showing on Android
// devices - an iPhone visitor can't install this file at all (a real
// Apple platform restriction, not a choice made here).
const ANDROID_APK_URL =
  'https://expo.dev/artifacts/eas/QTTx6yFzyUaiOI2_-YB_dn9H07unRQcbSiYWyTiQoas.apk';

// Real, persistent, anonymous device identifier - Koro's own confirmed
// design (2026-08-31) for every public Apprentice app: most visitors never
// create an account, so this is how the apprentice remembers a returning
// person (by device/browser, not name/login) without requiring one.
// Generated once, stored locally, reused on every future visit - never
// sent anywhere except this app's own backend. Dependency-free on purpose
// (no uuid/expo-crypto package) - a real, sufficiently-unique local ID,
// not a security token, so Math.random plus a timestamp is genuinely fine
// here.
const DEVICE_ID_KEY = 'apprentice_device_id';
function generateDeviceId() {
  return `dev-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
}
async function getOrCreateDeviceId() {
  try {
    const existing = await AsyncStorage.getItem(DEVICE_ID_KEY);
    if (existing) return existing;
    const created = generateDeviceId();
    await AsyncStorage.setItem(DEVICE_ID_KEY, created);
    return created;
  } catch {
    return generateDeviceId(); // still works this session even if storage is unavailable
  }
}

export default function App() {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);
  const [token, setToken] = useState(null);
  const [deviceId, setDeviceId] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [showAuth, setShowAuth] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [consent, setConsent] = useState(false);
  const [authError, setAuthError] = useState('');
  const [showAccount, setShowAccount] = useState(false);

  const authHeaders = (t) => (t ? { Authorization: `Bearer ${t}` } : {});

  useEffect(() => {
    getOrCreateDeviceId().then(setDeviceId);
  }, []);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem('apprentice_token');
      if (stored) {
        try {
          const res = await fetch(`${BACKEND_URL}/auth/me`, { headers: authHeaders(stored) });
          const data = await res.json();
          if (data.authenticated) {
            setToken(stored);
            const histRes = await fetch(`${BACKEND_URL}/conversations/history`, { headers: authHeaders(stored) });
            const histData = await histRes.json();
            if (histRes.ok && Array.isArray(histData.messages)) {
              setMessages(histData.messages.map((m) => ({ role: m.role === 'assistant' ? 'apprentice' : 'user', text: m.text })));
            }
          } else {
            await AsyncStorage.removeItem('apprentice_token');
          }
        } catch {
          // real, honest failure to verify a stored token - fall back to anonymous use
        }
      }
      setCheckingAuth(false);
    })();
  }, []);

  const submitAuth = async () => {
    setAuthError('');
    if (authMode === 'signup' && !consent) {
      setAuthError('Please agree to real data storage to create an account.');
      return;
    }
    try {
      const res = await fetch(`${BACKEND_URL}/auth/${authMode === 'signup' ? 'signup' : 'login'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, consent }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Something went wrong.');
      await AsyncStorage.setItem('apprentice_token', data.token);
      setToken(data.token);
      setShowAuth(false);
      setPassword('');
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const logout = async () => {
    if (token) fetch(`${BACKEND_URL}/auth/logout`, { method: 'POST', headers: authHeaders(token) }).catch(() => {});
    await AsyncStorage.removeItem('apprentice_token');
    setToken(null);
    setMessages([]);
    setShowAccount(false);
  };

  const deleteAccount = async () => {
    if (!token) return;
    try {
      await fetch(`${BACKEND_URL}/account/delete`, { method: 'POST', headers: authHeaders(token) });
    } catch {
      // proceed to clear local state regardless - the real deletion request was sent
    }
    await AsyncStorage.removeItem('apprentice_token');
    setToken(null);
    setMessages([]);
    setShowAccount(false);
  };

  const confirmDeleteAccount = () => {
    if (Platform.OS === 'web') {
      if (window.confirm('Permanently delete your account and every stored message? This cannot be undone.')) deleteAccount();
    } else {
      Alert.alert(
        'Delete account?',
        'This permanently deletes your account and every stored message. This cannot be undone.',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Delete', style: 'destructive', onPress: deleteAccount },
        ]
      );
    }
  };


  const ask = async () => {
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    const userMessage = { role: 'user', text: trimmed };
    setMessages((prev) => [...prev, userMessage]);
    setQuestion('');
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
        body: JSON.stringify({ question: trimmed, device_id: deviceId }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Something went wrong.');
      }
      setMessages((prev) => [...prev, { role: 'apprentice', text: data.answer }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'error', text: `Couldn't get an answer: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.title}>The Tohunga's Apprentice</Text>
        <Text style={{ fontSize: 13, color: '#7a6142', fontWeight: '600', marginTop: 2 }}>Aotearoa New Zealand — Maori tradition</Text>
        <Text style={styles.disclaimer}>{DISCLAIMER}</Text>
        {!token && (
          <Text style={styles.disclaimer}>
            No account needed - I remember our conversation on this device so you don't have to
            repeat yourself, even without signing in. If you tell me your name, I'll remember you
            personally next time; if someone else uses this device, just tell me a different name
            and I'll keep your conversations separate.
          </Text>
        )}
        {!checkingAuth && (
          token ? (
            <TouchableOpacity onPress={() => setShowAccount((v) => !v)}>
              <Text style={styles.acctLink}>Account</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity onPress={() => setShowAuth((v) => !v)}>
              <Text style={styles.acctLink}>{showAuth ? 'Close' : 'Remember me'}</Text>
            </TouchableOpacity>
          )
        )}
        {showAccount && token && (
          <View style={styles.acctPanel}>
            <Text style={styles.acctPanelText}>
              Signed in - I remember our real conversation history so you don't have to
              re-explain yourself. Delete your account any time to erase it permanently.
            </Text>
            <View style={styles.acctPanelRow}>
              <TouchableOpacity style={styles.acctSecondaryButton} onPress={logout}>
                <Text style={styles.acctSecondaryButtonText}>Log out</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.acctDangerButton} onPress={confirmDeleteAccount}>
                <Text style={styles.acctDangerButtonText}>Delete account</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
        {showAuth && !token && (
          <View style={styles.acctPanel}>
            <View style={styles.acctPanelRow}>
              <TouchableOpacity onPress={() => setAuthMode('login')}>
                <Text style={[styles.acctTab, authMode === 'login' && styles.acctTabActive]}>Log in</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setAuthMode('signup')}>
                <Text style={[styles.acctTab, authMode === 'signup' && styles.acctTabActive]}>Create account</Text>
              </TouchableOpacity>
            </View>
            <TextInput style={styles.acctInput} placeholder="Email" autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} />
            <TextInput style={styles.acctInput} placeholder="Password" secureTextEntry value={password} onChangeText={setPassword} />
            {authMode === 'signup' && (
              <View style={styles.acctConsentRow}>
                <Switch value={consent} onValueChange={setConsent} />
                <Text style={styles.acctConsentText}>
                  I want this apprentice to remember our conversation history (stored encrypted, deletable any time).
                </Text>
              </View>
            )}
            {!!authError && <Text style={styles.acctError}>{authError}</Text>}
            <TouchableOpacity style={styles.sendButton} onPress={submitAuth}>
              <Text style={styles.sendButtonText}>{authMode === 'signup' ? 'Create account' : 'Log in'}</Text>
            </TouchableOpacity>
          </View>
        )}
        <View style={{ flexDirection: 'row', marginTop: 8, gap: 16 }}>
          <TouchableOpacity onPress={() => Linking.openURL('https://taxapprentice.koroai.org')}>
            <Text style={{ fontSize: 12, textDecorationLine: 'underline', color: '#7a6142' }}>Tax help (any country)</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => Linking.openURL('https://tradies.koroai.org')}>
            <Text style={{ fontSize: 12, textDecorationLine: 'underline', color: '#7a6142' }}>Trade & electrical help</Text>
          </TouchableOpacity>
        </View>
        {Platform.OS === 'web' && (
          <TouchableOpacity
            style={styles.downloadButton}
            onPress={() => Linking.openURL(ANDROID_APK_URL)}
          >
            <Text style={styles.downloadButtonText}>⬇ Download for Android</Text>
          </TouchableOpacity>
        )}
      </View>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.flex}
          contentContainerStyle={styles.messages}
        >
          {messages.length === 0 && (
            <Text style={styles.empty}>
              Ask about tohunga traditions, tikanga, or kawa - e.g. "what is the
              difference between tikanga and kawa?" or "what happens at a pōwhiri?"
            </Text>
          )}
          {messages.map((m, i) => (
            <View
              key={i}
              style={[
                styles.bubble,
                m.role === 'user' ? styles.userBubble : styles.apprenticeBubble,
                m.role === 'error' && styles.errorBubble,
              ]}
            >
              <Text style={m.role === 'user' ? styles.userText : styles.apprenticeText}>
                {m.text}
              </Text>
            </View>
          ))}
          {loading && (
            <View style={styles.loadingRow}>
              <ActivityIndicator size="small" color="#7a4a2b" />
              <Text style={styles.loadingText}>Thinking, grounded in real sources...</Text>
            </View>
          )}
        </ScrollView>

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            placeholder="Ask a question..."
            value={question}
            onChangeText={setQuestion}
            onSubmitEditing={ask}
            multiline
          />
          <TouchableOpacity style={styles.sendButton} onPress={ask} disabled={loading}>
            <Text style={styles.sendButtonText}>Ask</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  acctLink: { color: '#1f7a6c', fontSize: 12, fontWeight: '700', marginTop: 6 },
  acctPanel: { marginTop: 10, padding: 12, backgroundColor: '#f5faf8', borderRadius: 10, borderWidth: 1, borderColor: '#d9ece6' },
  acctPanelText: { fontSize: 12, color: '#173a34', lineHeight: 17, marginBottom: 8 },
  acctPanelRow: { flexDirection: 'row', gap: 10, marginBottom: 6 },
  acctTab: { fontSize: 13, color: '#7a9c92', marginRight: 14, paddingBottom: 3 },
  acctTabActive: { color: '#173a34', fontWeight: '700', borderBottomWidth: 2, borderBottomColor: '#1f7a6c' },
  acctInput: { backgroundColor: '#fff', borderRadius: 8, borderWidth: 1, borderColor: '#d9ece6', paddingHorizontal: 10, paddingVertical: 7, marginTop: 6, fontSize: 13, color: '#173a34' },
  acctConsentRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  acctConsentText: { flex: 1, fontSize: 11, color: '#4d7a6e', lineHeight: 15 },
  acctError: { color: '#c0392b', fontSize: 11, marginTop: 6 },
  acctSecondaryButton: { backgroundColor: '#fff', borderRadius: 8, borderWidth: 1, borderColor: '#1f7a6c', paddingHorizontal: 12, paddingVertical: 7 },
  acctSecondaryButtonText: { color: '#1f7a6c', fontWeight: '600', fontSize: 12 },
  acctDangerButton: { backgroundColor: '#fff', borderRadius: 8, borderWidth: 1, borderColor: '#c0392b', paddingHorizontal: 12, paddingVertical: 7 },
  acctDangerButtonText: { color: '#c0392b', fontWeight: '600', fontSize: 12 },
  safe: { flex: 1, backgroundColor: '#fdf6ec' },
  flex: { flex: 1 },
  header: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#e5d5bb',
  },
  title: { fontSize: 20, fontWeight: '700', color: '#4a2f1c' },
  disclaimer: { fontSize: 12, color: '#7a6142', marginTop: 6, lineHeight: 17 },
  downloadButton: {
    marginTop: 10,
    alignSelf: 'flex-start',
    backgroundColor: '#e5d5bb',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  downloadButtonText: { color: '#4a2f1c', fontWeight: '600', fontSize: 13 },
  messages: { padding: 16, paddingBottom: 24 },
  empty: { color: '#9a8567', fontSize: 14, marginTop: 24, textAlign: 'center' },
  bubble: { borderRadius: 12, padding: 12, marginBottom: 10, maxWidth: '90%' },
  userBubble: { backgroundColor: '#4a2f1c', alignSelf: 'flex-end' },
  apprenticeBubble: { backgroundColor: '#fff', alignSelf: 'flex-start', borderWidth: 1, borderColor: '#e5d5bb' },
  errorBubble: { backgroundColor: '#fbe4e4', borderColor: '#e0a0a0' },
  userText: { color: '#fff', fontSize: 15 },
  apprenticeText: { color: '#3a2a1a', fontSize: 15, lineHeight: 21 },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  loadingText: { color: '#7a6142', fontSize: 13 },
  inputRow: {
    flexDirection: 'row',
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: '#e5d5bb',
    backgroundColor: '#fdf6ec',
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#e5d5bb',
    paddingHorizontal: 12,
    paddingVertical: 10,
    maxHeight: 120,
    fontSize: 15,
  },
  sendButton: {
    marginLeft: 8,
    backgroundColor: '#4a2f1c',
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  sendButtonText: { color: '#fff', fontWeight: '600' },
});
