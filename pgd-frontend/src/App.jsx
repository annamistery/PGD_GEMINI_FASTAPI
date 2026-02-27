import React, { useState, useRef } from "react";
import axios from "axios";
import { format } from "date-fns";
import "./App.css";

const DEFAULT_VOICE = "ru-RU-SvetlanaNeural";
const API_URL = import.meta.env.VITE_API_URL;

export default function App() {
  const [name, setName] = useState("");
  const [dob, setDob] = useState("");
  const [gender, setGender] = useState("Женский");

  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);

  const [displayText, setDisplayText] = useState(null);
  const [extendedText, setExtendedText] = useState(null);

  const [lastAudioBlob, setLastAudioBlob] = useState(null);
  const audioRef = useRef(null);

  const [chatHistory, setChatHistory] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [includeAttachmentsInChat, setIncludeAttachmentsInChat] = useState(false);

  const [attachments, setAttachments] = useState([]); // {id,name,file,previewUrl,text}
  const [linkInput, setLinkInput] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  // helpers
  const addAttachment = (file, previewUrl = null) => {
    const id = `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    setAttachments((p) => [
      ...p,
      {
        id,
        name: file.name || file,
        file: file instanceof File ? file : null,
        previewUrl,
        text: null,
      },
    ]);
  };

  const removeAttachment = (id) =>
    setAttachments((p) => p.filter((a) => a.id !== id));

  const uploadFileToServer = async (attachment) => {
    const form = new FormData();
    form.append("file", attachment.file, attachment.name);
    const resp = await fetch(`${API_URL}/upload_file`, {
      method: "POST",
      body: form,
    });
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(txt || "Upload failed");
    }
    return resp.json(); // { text, filename }
  };

  // TTS
  const generateAndStoreAudio = async (text, voice = DEFAULT_VOICE) => {
    try {
      const resp = await fetch(`${API_URL}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice }),
      });

      const contentType = resp.headers.get("content-type") || "";

      if (!resp.ok) {
        const errText = await resp.text();
        console.error("TTS HTTP error:", resp.status, errText);
        try {
          const parsed = JSON.parse(errText);
          if (parsed.error) alert(`Ошибка TTS: ${parsed.error}`);
          else alert("Ошибка TTS");
        } catch {
          alert("Ошибка TTS");
        }
        return null;
      }

      if (!contentType.includes("audio")) {
        const txt = await resp.text();
        console.error("TTS non-audio response:", txt);
        try {
          const parsed = JSON.parse(txt);
          if (parsed.error) alert(`Ошибка TTS: ${parsed.error}`);
          else alert("Ошибка TTS (не-аудио ответ)");
        } catch {
          alert("Ошибка TTS (не-аудио ответ)");
        }
        return null;
      }

      const blob = await resp.blob();
      console.log("TTS blob size:", blob.size);
      if (!blob.size) {
        alert("Пустой аудиофайл от TTS");
        return null;
      }

      setLastAudioBlob(blob);
      const url = URL.createObjectURL(blob);
      if (audioRef.current) audioRef.current.src = url;
      else audioRef.current = new Audio(url);
      return blob;
    } catch (e) {
      console.error(e);
      alert("Ошибка при генерации аудио");
      return null;
    }
  };

  const downloadAudio = () => {
    if (!lastAudioBlob) return;
    const url = URL.createObjectURL(lastAudioBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `PGD_Audio_${name}.mp3`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadText = () => {
    if (!displayText) return;
    const bom = "\uFEFF";
    const blob = new Blob([bom + displayText], {
      type: "text/plain;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `PGD_${name}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Base analysis
  const handleAnalyze = async () => {
    if (!name.trim() || !dob) {
      alert("Введите имя и дату рождения");
      return;
    }
    setIsProcessing(true);
    setProgress(5);
    setExtendedText(null);

    try {
      const payload = {
        name,
        dob: format(new Date(dob), "dd.MM.yyyy"),
        gender: gender === "Женский" ? "Ж" : "М",
      };

      setProgress(20);
      const resp = await axios.post(
        `${API_URL}/analyze_personality`,
        payload,
        { timeout: 120000 },
      );
      setProgress(70);

      if (resp.data?.error) {
        alert("Ошибка анализа: " + resp.data.error);
        setDisplayText(null);
        setIsProcessing(false);
        setProgress(0);
        return;
      }

      setDisplayText(resp.data.display_text || "ИИ не вернул интерпретацию.");
      setProgress(95);

      const textForTts = resp.data.display_text || "";
      if (textForTts) await generateAndStoreAudio(textForTts, DEFAULT_VOICE);

      setProgress(100);
    } catch (err) {
      console.error("handleAnalyze:", err);
      alert("Ошибка при запросе анализа");
    } finally {
      setIsProcessing(false);
      setTimeout(() => setProgress(0), 600);
    }
  };

  // Add link
  const handleAddLink = async () => {
    if (!linkInput.trim()) return;
    setIsUploading(true);
    try {
      const resp = await axios.post(`${API_URL}/fetch_url_text`, {
        url: linkInput,
      });
      const text = resp.data.text || "";
      const id = `link_${Date.now()}_${Math.random()
        .toString(36)
        .slice(2, 6)}`;
      setAttachments((p) => [
        ...p,
        { id, name: linkInput, file: null, previewUrl: null, text },
      ]);
      setLinkInput("");
    } catch (err) {
      console.error("fetch_url_text error", err);
      alert(
        "Не удалось получить документ по ссылке. Убедитесь, что документ публичен или загрузите файл напрямую.",
      );
    } finally {
      setIsUploading(false);
    }
  };

  // Extended analysis
  const handleExtendedAnalysis = async () => {
    if (!displayText) {
      alert("Сначала выполните базовый анализ.");
      return;
    }
    setIsUploading(true);
    try {
      const updated = await Promise.all(
        attachments.map(async (a) => {
          if (a.text) return a;
          if (!a.file) return a;
          try {
            const data = await uploadFileToServer(a);
            return { ...a, text: data.text || "" };
          } catch (e) {
            console.warn("upload failed for", a.name, e);
            return { ...a, text: "" };
          }
        }),
      );
      setAttachments(updated);

      const attachmentsText = updated
        .map((a) => (a.text ? `--- ${a.name} ---\n${a.text}\n` : ""))
        .join("\n");

      const payload = {
        base_report: displayText,
        attachments_text: attachmentsText,
        user_name: name,
      };

      const resp = await axios.post(
        `${API_URL}/extended_analysis`,
        payload,
        { timeout: 180000 },
      );
      if (resp.data?.error) {
        alert("Ошибка расширенного анализа: " + resp.data.error);
        setExtendedText(null);
      } else {
        setExtendedText(resp.data.extended || "Нет расширенного анализа");
        if (resp.data.extended)
          await generateAndStoreAudio(resp.data.extended, DEFAULT_VOICE);
      }
    } catch (err) {
      console.error("handleExtendedAnalysis:", err);
      alert("Ошибка при расширенном анализе");
    } finally {
      setIsUploading(false);
    }
  };

  // Chat
  const handleChatSubmit = async () => {
    if (!chatInput.trim()) return;
    if (!displayText) {
      alert("Сначала выполните базовый анализ.");
      return;
    }

    const userMsg = { role: "user", content: chatInput };
    setChatHistory((p) => [...p, userMsg]);

    try {
      let context = displayText;
      if (includeAttachmentsInChat) {
        setIsUploading(true);
        const updated = await Promise.all(
          attachments.map(async (a) => {
            if (a.text) return a;
            if (!a.file) return a;
            try {
              const data = await uploadFileToServer(a);
              return { ...a, text: data.text || "" };
            } catch {
              return { ...a, text: "" };
            }
          }),
        );
        setAttachments(updated);
        setIsUploading(false);
        const attachmentsText = updated
          .map((a) => (a.text ? `--- ${a.name} ---\n${a.text}\n` : ""))
          .join("\n");
        context = (context || "") + "\n\n" + attachmentsText;
      }

      const resp = await axios.post(`${API_URL}/chat`, {
        query: chatInput,
        context,
        user_name: name,
      });

      const assistant = {
        role: "assistant",
        content: resp.data.reply || "Пустой ответ",
      };
      setChatHistory((p) => [...p, assistant]);
    } catch (err) {
      console.error("handleChatSubmit:", err);
      setChatHistory((p) => [
        ...p,
        { role: "assistant", content: "Ошибка при обработке вопроса" },
      ]);
    } finally {
      setChatInput("");
    }
  };

  const handleFilesSelected = (e) => {
    const files = Array.from(e.target.files || []);
    files.forEach((file) => {
      if (file.type.startsWith("image/")) {
        const url = URL.createObjectURL(file);
        addAttachment(file, url);
      } else {
        addAttachment(file, null);
      }
    });
    e.target.value = null;
  };

  return (
    <div className="app" style={{ fontFamily: "Inter, sans-serif", padding: 20 }}>
      <header style={{ marginBottom: 18 }}>
        <h1>🌟 Проективная психогенетическая карта личности</h1>
        <div style={{ color: "#666", marginTop: 6 }}>
          Базовый анализ выполняется только по имени, дате рождения и полу. Вложения используются опционально — для расширенного анализа и/или в чате.
        </div>
      </header>

      <div style={{ display: "flex", gap: 20 }}>
        {/* Sidebar */}
        <aside style={{ width: 340, borderRight: "1px solid #eee", paddingRight: 16 }}>
          <h3>📋 Данные</h3>

          <label style={{ display: "block", marginTop: 8 }}>Имя</label>
          <input value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%", padding: 8 }} />

          <label style={{ display: "block", marginTop: 12 }}>Дата рождения</label>
          <input type="date" value={dob} onChange={(e) => setDob(e.target.value)} style={{ width: "100%", padding: 8 }} />

          <label style={{ display: "block", marginTop: 12 }}>Пол</label>
          <div>
            <label style={{ marginRight: 12 }}>
              <input type="radio" checked={gender === "Женский"} onChange={() => setGender("Женский")} /> Женский
            </label>
            <label>
              <input type="radio" checked={gender === "Мужской"} onChange={() => setGender("Мужской")} /> Мужской
            </label>
          </div>

          <div style={{ marginTop: 16 }}>
            <button onClick={handleAnalyze} disabled={isProcessing} style={{ padding: "10px 14px" }}>
              {isProcessing ? "🚀 Анализирую..." : "🚀 Запустить базовый анализ"}
            </button>
          </div>

          {isProcessing && (
            <div style={{ marginTop: 12 }}>
              <div style={{ height: 8, background: "#eee", borderRadius: 6 }}>
                <div style={{ width: `${progress}%`, height: "100%", background: "#4fc3f7", borderRadius: 6 }} />
              </div>
              <div style={{ marginTop: 6, fontSize: 13 }}>{progress}%</div>
            </div>
          )}

          <hr style={{ margin: "18px 0" }} />

          <h4>📎 Вложения (опционально)</h4>
          <input type="file" multiple onChange={handleFilesSelected} />
          <div style={{ marginTop: 8 }}>
            <input
              placeholder="Вставьте ссылку на документ"
              value={linkInput}
              onChange={(e) => setLinkInput(e.target.value)}
              style={{ width: "100%", padding: 8 }}
            />
            <button onClick={handleAddLink} disabled={isUploading} style={{ marginTop: 8 }}>
              Добавить ссылку
            </button>
          </div>

          <div style={{ marginTop: 12 }}>
            <button onClick={handleExtendedAnalysis} disabled={isUploading || isProcessing}>
              {isUploading ? "Загружаю вложения..." : "🔎 Расширенный анализ с моими документами"}
            </button>
          </div>
        </aside>

        {/* Main */}
        <main style={{ flex: 1 }}>
          {/* Attachments list */}
          <section style={{ marginBottom: 12 }}>
            <h3>Вложения</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {attachments.length === 0 && (
                <div style={{ background: "#E6E0F8", color: "#2b2b2b", padding: 12, borderRadius: 8 }}>Нет вложений</div>
              )}
              {attachments.map((a) => (
                <div
                  key={a.id}
                  style={{ display: "flex", gap: 8, alignItems: "center", background: "#f7f7fb", padding: 8, borderRadius: 8 }}
                >
                  {a.previewUrl ? (
                    <img src={a.previewUrl} alt={a.name} style={{ width: 96, height: 72, objectFit: "cover", borderRadius: 6 }} />
                  ) : (
                    <div
                      style={{
                        width: 96,
                        height: 72,
                        background: "#eee",
                        borderRadius: 6,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      DOC
                    </div>
                  )}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600 }}>{a.name}</div>
                    <div style={{ fontSize: 13, color: "#666" }}>
                      {a.text ? `${a.text.slice(0, 200)}${a.text.length > 200 ? "…" : ""}` : "Текст ещё не извлечён"}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <button
                      onClick={async () => {
                        if (!a.text && a.file) {
                          try {
                            const data = await uploadFileToServer(a);
                            setAttachments((prev) =>
                              prev.map((x) => (x.id === a.id ? { ...x, text: data.text || "" } : x)),
                            );
                          } catch (e) {
                            alert("Ошибка загрузки");
                          }
                        } else if (a.text) {
                          await generateAndStoreAudio(a.text, DEFAULT_VOICE);
                        }
                      }}
                    >
                      {a.text ? "🔊 Озвучить" : "⬆️ Извлечь текст"}
                    </button>
                    <button onClick={() => removeAttachment(a.id)}>Удалить</button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Analysis */}
          <section style={{ marginBottom: 20 }}>
            <h2>📄 Интерпретация ИИ</h2>
            {displayText ? (
              <>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
                  <button onClick={() => generateAndStoreAudio(displayText, DEFAULT_VOICE)}>🔊 Озвучить (Svetlana)</button>
                  <button
                    onClick={() => {
                      if (audioRef.current) audioRef.current.play();
                    }}
                    disabled={!lastAudioBlob}
                  >
                    ▶ Воспроизвести
                  </button>
                  <button
                    onClick={() => {
                      if (audioRef.current) audioRef.current.pause();
                    }}
                    disabled={!lastAudioBlob}
                  >
                    ⏸ Пауза
                  </button>
                  {lastAudioBlob && <button onClick={downloadAudio}>💾 Скачать аудио</button>}
                  <button onClick={downloadText}>💾 Скачать текст</button>
                </div>

                <div style={{ background: "#fafafa", padding: 12, borderRadius: 8, whiteSpace: "pre-wrap" }}>{displayText}</div>

                <audio ref={audioRef} controls style={{ marginTop: 12, width: "100%" }} />
              </>
            ) : (
              <div style={{ background: "#E6E0F8", padding: 12, borderRadius: 8 }}>
                <div style={{ color: "#2b2b2b", fontSize: 15 }}>Запустите анализ, чтобы увидеть интерпретацию ИИ.</div>
              </div>
            )}
          </section>

          {/* Extended analysis */}
          {extendedText && (
            <section style={{ marginBottom: 20 }}>
              <h2>🔎 Расширенный анализ (с учётом ваших документов)</h2>
              <div style={{ background: "#fff8f0", padding: 12, borderRadius: 8, whiteSpace: "pre-wrap" }}>{extendedText}</div>
            </section>
          )}

          {/* Chat */}
          <section>
            <h2>💬 Диалог</h2>

            <div
              style={{
                maxHeight: 320,
                overflowY: "auto",
                padding: 8,
                border: "1px solid #eee",
                borderRadius: 8,
                marginBottom: 12,
                background: "#fff",
              }}
            >
              {chatHistory.length === 0 ? (
                <div
                  style={{
                    background: "#E6E0F8",
                    color: "#2b2b2b",
                    padding: 12,
                    borderRadius: 8,
                  }}
                >
                  Здесь будут сообщения чата.
                </div>
              ) : (
                chatHistory.map((m, i) => (
                  <div key={i} style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 12, color: "#666" }}>
                      {m.role === "user" ? "Вы" : "Ассистент"}
                    </div>
                    <div
                      style={{
                        background: m.role === "user" ? "#e6f7ff" : "#f5f5f5",
                        padding: 10,
                        borderRadius: 8,
                      }}
                    >
                      {m.content}
                    </div>
                    {m.role === "assistant" && (
                      <div style={{ marginTop: 6 }}>
                        <button
                          onClick={() => generateAndStoreAudio(m.content, DEFAULT_VOICE)}
                          style={{ marginRight: 8 }}
                        >
                          🔊 Озвучить
                        </button>
                        <button
                          onClick={async () => {
                            await generateAndStoreAudio(m.content, DEFAULT_VOICE);
                            downloadAudio();
                          }}
                        >
                          💾 Скачать
                        </button>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleChatSubmit();
                }}
                placeholder="Задайте уточняющий вопрос..."
                style={{ flex: 1, padding: 10 }}
              />
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input
                  type="checkbox"
                  checked={includeAttachmentsInChat}
                  onChange={(e) => setIncludeAttachmentsInChat(e.target.checked)}
                />
                Включать вложения
              </label>
              <button onClick={handleChatSubmit}>Отправить</button>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
