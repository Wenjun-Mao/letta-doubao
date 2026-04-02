const { createApp } = Vue

createApp({
    data() {
        return {
            agentId: '',
            userInput: '',
            isChatting: false,
            isCreating: false,
            isFetchingDetails: false,
            optionsLoading: false,
            showLeftSidebar: true,
            leftTab: 'model', // model | prompt | tools
            chatHistory: [],
            lastResult: null,
            agentDetails: null,

            availableModels: [],
            availableEmbeddings: [],
            availablePrompts: [],
            serverDefaultEmbedding: '',
            selectedModel: '',
            selectedEmbedding: '',
            selectedPromptKey: '',
            newAgentName: 'dev-agent',
            existingAgents: [],
            existingAgentsLoading: false,
            selectedExistingAgentId: '',
            
            showRawPrompt: false,
            rawPromptData: null,
            showPersistentState: false,
            persistentState: null,
            persistentLoading: false,
            persistentError: '',
            persistentTab: 'summary', // summary | memory | history
            persistentLimit: 120,
        }
    },
    computed: {
        selectedExistingAgent() {
            return this.existingAgents.find(item => item.id === this.selectedExistingAgentId) || null;
        }
    },
    async mounted() {
        await this.fetchOptions();
        await this.fetchExistingAgents();

        const storedModel = localStorage.getItem('letta_selected_model');
        if (storedModel && this.availableModels.some(model => model.key === storedModel)) {
            this.selectedModel = storedModel;
        }

        const storedPrompt = localStorage.getItem('letta_selected_prompt_key');
        if (storedPrompt && this.availablePrompts.some(prompt => prompt.key === storedPrompt)) {
            this.selectedPromptKey = storedPrompt;
        }

        const storedEmbedding = localStorage.getItem('letta_selected_embedding');
        if (storedEmbedding !== null) {
            const isKnown = this.availableEmbeddings.some(embedding => embedding.key === storedEmbedding);
            this.selectedEmbedding = isKnown ? storedEmbedding : '';
        }

        const storedName = localStorage.getItem('letta_new_agent_name');
        if (storedName !== null) {
            this.newAgentName = storedName;
        }

        // Check if agent id is in local storage to resume
        const stored = localStorage.getItem('letta_agent_id');
        if (stored) {
            this.agentId = stored;
            this.fetchAgentDetails();
        }
    },
    watch: {
        agentId(val, oldVal) {
            localStorage.setItem('letta_agent_id', val);
            this.selectedExistingAgentId = val || '';
            if (val !== oldVal) {
                this.rawPromptData = null;
                this.persistentState = null;
                this.persistentError = '';
            }
        },
        selectedModel(val) {
            localStorage.setItem('letta_selected_model', val);
        },
        selectedPromptKey(val) {
            localStorage.setItem('letta_selected_prompt_key', val);
        },
        selectedEmbedding(val) {
            localStorage.setItem('letta_selected_embedding', val || '');
        },
        newAgentName(val) {
            localStorage.setItem('letta_new_agent_name', val);
        }
    },
    methods: {
        modelOptionLabel(option) {
            if (!option) return '';
            return option.available === false ? `${option.label} (not registered)` : option.label;
        },
        embeddingOptionLabel(option) {
            if (!option) return '';
            const base = option.available === false ? `${option.label} (not registered)` : option.label;
            if (option.is_default || (this.serverDefaultEmbedding && option.key === this.serverDefaultEmbedding)) {
                return `${base} (letta server default)`;
            }
            return base;
        },
        embeddingPlaceholderLabel() {
            return this.serverDefaultEmbedding ? 'Use Letta server default' : 'Use Letta server default (letta server default)';
        },
        shortId(value) {
            const id = String(value || '');
            if (id.length <= 28) {
                return id;
            }
            return `${id.slice(0, 14)}...${id.slice(-8)}`;
        },
        formatTimestamp(value) {
            if (!value) {
                return 'N/A';
            }
            const date = new Date(value);
            if (Number.isNaN(date.getTime())) {
                return String(value);
            }
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false,
            });
        },
        existingAgentOptionLabel(item) {
            const name = item?.name || '(unnamed)';
            const created = this.formatTimestamp(item?.created_at);
            const last = this.formatTimestamp(item?.last_interaction_at || item?.last_updated_at);
            return `${name} · ${this.shortId(item?.id)} · C:${created} · L:${last}`;
        },
        prettyJson(value) {
            if (value === null || value === undefined) {
                return '';
            }
            if (typeof value === 'string') {
                return value;
            }
            try {
                return JSON.stringify(value, null, 2);
            } catch {
                return String(value);
            }
        },
        togglePersistentState() {
            this.showPersistentState = !this.showPersistentState;
            if (this.showPersistentState && this.agentId && !this.persistentState) {
                this.fetchPersistentState();
            }
        },
        async fetchOptions() {
            this.optionsLoading = true;
            try {
                const res = await axios.get('/api/options');
                this.availableModels = res.data.models || [];
                this.availableEmbeddings = res.data.embeddings || [];
                this.availablePrompts = res.data.prompts || [];
                this.serverDefaultEmbedding = res.data.defaults?.embedding || '';

                if (!this.selectedModel) {
                    this.selectedModel = res.data.defaults?.model || '';
                }
                if (this.selectedEmbedding === '') {
                    this.selectedEmbedding = res.data.defaults?.embedding || '';
                }
                if (!this.selectedPromptKey) {
                    this.selectedPromptKey = res.data.defaults?.prompt_key || '';
                }
            } catch (e) {
                console.error('Failed to load model/prompt options', e);
            }
            this.optionsLoading = false;
        },
        async fetchExistingAgents() {
            this.existingAgentsLoading = true;
            try {
                const res = await axios.get('/api/agents?limit=200');
                this.existingAgents = res.data.items || [];

                if (this.agentId && this.existingAgents.some(item => item.id === this.agentId)) {
                    this.selectedExistingAgentId = this.agentId;
                }
            } catch (e) {
                console.error('Failed to load existing agents', e);
            } finally {
                this.existingAgentsLoading = false;
            }
        },
        async createAgent() {
            this.isCreating = true;
            try {
                const res = await axios.post('/api/agents', {
                    name: this.newAgentName.trim() || 'dev-agent',
                    model: this.selectedModel,
                    embedding: this.selectedEmbedding || null,
                    prompt_key: this.selectedPromptKey,
                });
                this.agentId = res.data.id;
                await this.fetchAgentDetails();
                this.chatHistory = [];
                this.lastResult = null;
                this.rawPromptData = null;
                this.persistentState = null;
                this.persistentError = '';
                this.selectedExistingAgentId = this.agentId;
                await this.fetchExistingAgents();
            } catch (e) {
                const detail = e?.response?.data?.detail || e.message;
                alert("Error creating agent: " + detail);
            }
            this.isCreating = false;
        },
        async fetchAgentDetails() {
            if (!this.agentId) return;
            this.isFetchingDetails = true;
            try {
                const res = await axios.get(`/api/agents/${this.agentId}/details`);
                this.agentDetails = res.data;
            } catch (e) {
                console.error("Failed to load details");
            }
            this.isFetchingDetails = false;
        },
        async fetchRawPrompt() {
            if (!this.agentId) return;
            try {
                const res = await axios.get(`/api/agents/${this.agentId}/raw_prompt`);
                this.rawPromptData = res.data.messages;
            } catch (e) {
                alert('Could not fetch context');
            }
        },
        async pullExistingInfo(agentId = '') {
            const targetAgentId = (agentId || this.selectedExistingAgentId || '').trim();
            if (!targetAgentId) {
                return;
            }

            this.agentId = targetAgentId;
            await this.fetchAgentDetails();
            this.showPersistentState = true;
            await this.fetchPersistentState({ hydrateChat: true });
        },
        hydrateChatHistoryFromPersistent() {
            const items = this.persistentState?.conversation_history?.items || [];
            const hydrated = [];

            for (const item of items) {
                const messageType = (item.message_type || '').toLowerCase();
                const rawContent = typeof item.content === 'string' ? item.content : String(item.content ?? '');
                const content = rawContent.replace(/\r\n/g, '\n');
                if (!content.trim()) {
                    continue;
                }

                if (messageType === 'user_message') {
                    hydrated.push({ role: 'user', content });
                } else if (messageType === 'assistant_message') {
                    hydrated.push({ role: 'assistant', content });
                }
            }

            if (hydrated.length > 0) {
                this.chatHistory = hydrated.filter(msg => String(msg.content || '').trim());
            }
        },
        async fetchPersistentState(options = {}) {
            const { hydrateChat = false } = options;
            if (!this.agentId) return;
            this.persistentLoading = true;
            this.persistentError = '';
            try {
                const url = `/api/agents/${this.agentId}/persistent_state?limit=${this.persistentLimit}`;
                const res = await axios.get(url);
                this.persistentState = res.data;
                if (hydrateChat) {
                    this.hydrateChatHistoryFromPersistent();
                }
            } catch (e) {
                this.persistentError = e?.response?.data?.detail || e.message || 'Failed to fetch backend persistent state';
            } finally {
                this.persistentLoading = false;
            }
        },
        async sendMessage() {
            if (!this.userInput.trim() || !this.agentId || this.isChatting) return;
            
            const messageText = this.userInput.trim();
            this.chatHistory.push({ role: 'user', content: messageText });
            this.userInput = '';
            this.isChatting = true;
            this.rawPromptData = null; // reset prompt trace

            this.$nextTick(() => {
                const container = document.getElementById('chat-container');
                container.scrollTop = container.scrollHeight;
            });

            try {
                const res = await axios.post('/api/chat', {
                    agent_id: this.agentId,
                    message: messageText
                });
                
                this.lastResult = res.data;
                
                // Extract assistant message to show in UI
                const responseMsg = res.data.sequence.find(s => s.type === 'assistant');
                if (responseMsg && String(responseMsg.content || '').trim()) {
                    this.chatHistory.push({ role: 'assistant', content: responseMsg.content });
                }

                // Auto-refresh agent details if memory changed
                if (JSON.stringify(res.data.memory_diff.old) !== JSON.stringify(res.data.memory_diff.new)) {
                    this.fetchAgentDetails();
                }

                if (this.showPersistentState) {
                    this.fetchPersistentState();
                }

            } catch (err) {
                this.chatHistory.push({ role: 'assistant', content: '❌ Error: Failed to communicate with agent backend.' });
            } finally {
                this.isChatting = false;
                this.$nextTick(() => {
                    const container = document.getElementById('chat-container');
                    container.scrollTop = container.scrollHeight;
                });
            }
        },
        escapeHtml(text) {
            return String(text)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");
        },
        diffSequence(source, target) {
            const m = source.length;
            const n = target.length;
            const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));

            for (let i = 1; i <= m; i++) {
                for (let j = 1; j <= n; j++) {
                    if (source[i - 1] === target[j - 1]) {
                        dp[i][j] = dp[i - 1][j - 1] + 1;
                    } else {
                        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
                    }
                }
            }

            const ops = [];
            let i = m;
            let j = n;

            while (i > 0 || j > 0) {
                if (i > 0 && j > 0 && source[i - 1] === target[j - 1]) {
                    ops.push({ type: "equal", value: source[i - 1] });
                    i -= 1;
                    j -= 1;
                    continue;
                }

                if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
                    ops.push({ type: "insert", value: target[j - 1] });
                    j -= 1;
                } else {
                    ops.push({ type: "delete", value: source[i - 1] });
                    i -= 1;
                }
            }

            return ops.reverse();
        },
        renderInlineDiff(oldLine, newLine) {
            const charOps = this.diffSequence([...oldLine], [...newLine]);
            let oldHtml = "";
            let newHtml = "";

            for (const op of charOps) {
                const escaped = this.escapeHtml(op.value);
                if (op.type === "equal") {
                    oldHtml += escaped;
                    newHtml += escaped;
                } else if (op.type === "delete") {
                    oldHtml += `<span class=\"diff-removed\">${escaped}</span>`;
                } else if (op.type === "insert") {
                    newHtml += `<span class=\"diff-added\">${escaped}</span>`;
                }
            }

            return { oldHtml, newHtml };
        },
        highlightDiff(oldText, newText) {
            const oldValue = oldText || "";
            const newValue = newText || "";

            if (oldValue === newValue) {
                return `<div class=\"diff-line\">${this.escapeHtml(newValue)}</div>`;
            }

            const oldLines = oldValue.split("\n");
            const newLines = newValue.split("\n");
            const lineOps = this.diffSequence(oldLines, newLines);

            const chunks = [];
            let idx = 0;
            while (idx < lineOps.length) {
                const current = lineOps[idx];

                if (current.type === "equal") {
                    chunks.push(`<div class=\"diff-line\">${this.escapeHtml(current.value)}</div>`);
                    idx += 1;
                    continue;
                }

                const next = lineOps[idx + 1];
                if (current.type === "delete" && next && next.type === "insert") {
                    const inline = this.renderInlineDiff(current.value, next.value);
                    chunks.push(`<div class=\"diff-line diff-line-removed\"><span class=\"diff-marker\">[-]</span>${inline.oldHtml || " "}</div>`);
                    chunks.push(`<div class=\"diff-line diff-line-added\"><span class=\"diff-marker\">[+]</span>${inline.newHtml || " "}</div>`);
                    idx += 2;
                    continue;
                }

                if (current.type === "insert" && next && next.type === "delete") {
                    const inline = this.renderInlineDiff(next.value, current.value);
                    chunks.push(`<div class=\"diff-line diff-line-removed\"><span class=\"diff-marker\">[-]</span>${inline.oldHtml || " "}</div>`);
                    chunks.push(`<div class=\"diff-line diff-line-added\"><span class=\"diff-marker\">[+]</span>${inline.newHtml || " "}</div>`);
                    idx += 2;
                    continue;
                }

                if (current.type === "delete") {
                    chunks.push(`<div class=\"diff-line diff-line-removed\"><span class=\"diff-marker\">[-]</span><span class=\"diff-removed\">${this.escapeHtml(current.value)}</span></div>`);
                } else if (current.type === "insert") {
                    chunks.push(`<div class=\"diff-line diff-line-added\"><span class=\"diff-marker\">[+]</span><span class=\"diff-added\">${this.escapeHtml(current.value)}</span></div>`);
                }

                idx += 1;
            }

            return chunks.join("");
        }
    }
}).mount('#app')
