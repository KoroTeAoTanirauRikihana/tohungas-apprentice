import { useState, useRef } from 'react';
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
  Linking,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';

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

export default function App() {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);

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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed }),
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
        <Text style={styles.disclaimer}>{DISCLAIMER}</Text>
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
