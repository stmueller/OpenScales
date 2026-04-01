/**
 * osd2surveydown.js — Convert OpenScales .osd JSON to surveydown format
 *
 * Client-side converter that produces questions.yml, survey.qmd, and app.R
 * from an OSD definition object.
 */

class OSD2Surveydown {

    constructor(osdData, lang = 'en') {
        this.osd = osdData;
        this.defn = osdData.definition || {};
        this.translations = (osdData.translations || {})[lang] || {};
        this.lang = lang;
        this.scaleInfo = this.defn.scale_info || {};
        this.items = this.defn.items || [];
        this.likertOptions = this.defn.likert_options || {};
    }

    resolveText(key) {
        return this.translations[key] || key;
    }

    yamlEscape(text) {
        if (!text) return '""';
        text = String(text);
        if (/[:#{}[\],&*?|<>=!%@`"'\n]/.test(text)) {
            const escaped = text.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n');
            return `"${escaped}"`;
        }
        return text;
    }

    // ── Item converters ──────────────────────────────────────────────

    convertLikert(item) {
        const lo = this.likertOptions;
        const points = item.likert_points || lo.points || 5;
        const minVal = item.likert_min || lo.min || 1;
        const maxVal = item.likert_max || lo.max || points;
        const labels = item.likert_labels || lo.labels || [];

        let text = this.resolveText(item.text_key || item.id);
        const qheadKey = item.question_head || lo.question_head || '';
        if (qheadKey) {
            const qhead = this.resolveText(qheadKey);
            if (qhead) text = qhead + '\n\n' + text;
        }

        const options = {};
        for (let v = minVal; v <= maxVal; v++) {
            const idx = v - minVal;
            const label = idx < labels.length ? this.resolveText(labels[idx]) : String(v);
            options[label] = String(v);
        }

        return { type: 'mc', label: text, options };
    }

    convertVas(item) {
        const text = this.resolveText(item.text_key || item.id);
        const minVal = item.min || 0;
        const maxVal = item.max || 100;
        const step = item.step || 1;
        const minLabel = this.resolveText(item.min_label || '');
        const maxLabel = this.resolveText(item.max_label || '');

        const options = {};
        for (let v = minVal; v <= maxVal; v += step) {
            if (v === minVal && minLabel && minLabel !== item.min_label) {
                options[minLabel] = String(v);
            } else if (v === maxVal && maxLabel && maxLabel !== item.max_label) {
                options[maxLabel] = String(v);
            } else {
                options[String(v)] = String(v);
            }
        }

        return { type: 'slider', label: text, options };
    }

    convertMulti(item) {
        const text = this.resolveText(item.text_key || item.id);
        const options = {};
        for (const opt of (item.options || [])) {
            if (typeof opt === 'object') {
                const optText = this.resolveText(opt.text_key || opt.value || '');
                options[optText] = String(opt.value || '');
            } else {
                const optText = this.resolveText(String(opt));
                options[optText] = String(opt);
            }
        }
        return { type: 'mc', label: text, options };
    }

    convertMulticheck(item) {
        const result = this.convertMulti(item);
        result.type = 'mc_multiple';
        return result;
    }

    convertShort(item) {
        const text = this.resolveText(item.text_key || item.id);
        const result = { type: 'text', label: text };
        if (item.maxlength) result.placeholder = `Max ${item.maxlength} characters`;
        return result;
    }

    convertLong(item) {
        const text = this.resolveText(item.text_key || item.id);
        return { type: 'textarea', label: text };
    }

    convertGrid(item) {
        const text = this.resolveText(item.text_key || item.id);
        const rows = {};
        for (const row of (item.rows || [])) {
            if (typeof row === 'object') {
                rows[this.resolveText(row.text_key || row.id || '')] = row.id || '';
            } else {
                rows[this.resolveText(String(row))] = String(row);
            }
        }
        const options = {};
        for (const col of (item.columns || [])) {
            if (typeof col === 'object') {
                options[this.resolveText(col.text_key || col.label || '')] = String(col.value || '');
            } else {
                options[this.resolveText(String(col))] = String(col);
            }
        }
        return { type: 'matrix', label: text, row: rows, options };
    }

    convertItem(item) {
        const converters = {
            likert: (i) => this.convertLikert(i),
            vas: (i) => this.convertVas(i),
            multi: (i) => this.convertMulti(i),
            multicheck: (i) => this.convertMulticheck(i),
            short: (i) => this.convertShort(i),
            long: (i) => this.convertLong(i),
            grid: (i) => this.convertGrid(i),
        };
        const fn = converters[item.type];
        return fn ? fn(item) : null;
    }

    // ── File generators ──────────────────────────────────────────────

    generateQuestionsYml() {
        const lines = [];
        lines.push(`# Auto-generated from ${this.scaleInfo.code || 'unknown'}.osd`);
        lines.push(`# Language: ${this.lang}`);
        lines.push('');

        for (const item of this.items) {
            if (['section', 'inst'].includes(item.type)) continue;

            const sd = this.convertItem(item);
            if (!sd) {
                lines.push(`# SKIPPED: ${item.id} (unsupported type: ${item.type})`);
                lines.push('');
                continue;
            }

            lines.push(`${item.id}:`);
            for (const [key, value] of Object.entries(sd)) {
                if (typeof value === 'object') {
                    lines.push(`  ${key}:`);
                    for (const [k, v] of Object.entries(value)) {
                        lines.push(`    ${this.yamlEscape(k)}: ${this.yamlEscape(v)}`);
                    }
                } else if (typeof value === 'boolean') {
                    lines.push(`  ${key}: ${value}`);
                } else {
                    lines.push(`  ${key}: ${this.yamlEscape(value)}`);
                }
            }
            if (item.required) lines.push('  required: true');
            lines.push('');
        }

        return lines.join('\n');
    }

    generateSurveyQmd() {
        const lines = [];
        lines.push('---');
        lines.push('format: html');
        lines.push('echo: false');
        lines.push('warning: false');
        lines.push('---');
        lines.push('');
        lines.push('```{r}');
        lines.push('library(surveydown)');
        lines.push('```');
        lines.push('');

        let pageNum = 1;
        let inPage = false;

        for (const item of this.items) {
            if (item.type === 'section') {
                if (inPage) { lines.push(':::'); lines.push(''); }
                const title = this.resolveText(item.text_key || '');
                lines.push(`::: {#page${pageNum} .sd-page}`);
                lines.push('');
                if (title) { lines.push(`## ${title}`); lines.push(''); }
                inPage = true;
                pageNum++;
            } else if (item.type === 'inst') {
                if (!inPage) {
                    lines.push(`::: {#page${pageNum} .sd-page}`);
                    lines.push('');
                    inPage = true;
                    pageNum++;
                }
                const text = this.resolveText(item.text_key || '');
                if (text) { lines.push(text); lines.push(''); }
            } else {
                if (!inPage) {
                    lines.push(`::: {#page${pageNum} .sd-page}`);
                    lines.push('');
                    inPage = true;
                    pageNum++;
                }
                lines.push('```{r}');
                lines.push(`sd_question("${item.id}")`);
                lines.push('```');
                lines.push('');
            }
        }

        if (inPage) { lines.push(':::'); lines.push(''); }

        lines.push(`::: {#end .sd-page}`);
        lines.push('');
        lines.push(`## ${this.scaleInfo.name || 'Survey'} Complete`);
        lines.push('');
        lines.push('Thank you for completing this survey.');
        lines.push('');
        lines.push('```{r}');
        lines.push('sd_close()');
        lines.push('```');
        lines.push(':::');
        lines.push('');

        return lines.join('\n');
    }

    generateAppR() {
        const code = this.scaleInfo.code || 'survey';
        return `# app.R — ${this.scaleInfo.name || 'Survey'}
# Auto-generated from ${code}.osd by osd2surveydown

library(surveydown)

# Database connection
# For local testing, use ignore = TRUE (saves to local CSV)
# For production, configure .env file with database credentials
db <- sd_db_connect(ignore = TRUE)

# Server configuration
server <- function(input, output, session) {

  # Define conditional display / skip logic here if needed
  # sd_show_if(condition, "question_id")
  # sd_skip_if(condition, "page_id")

  sd_server(db = db)
}

# Run the app
shiny::shinyApp(ui = sd_ui(), server = server)
`;
    }

    // ── Main conversion ──────────────────────────────────────────────

    convert() {
        return {
            'questions.yml': this.generateQuestionsYml(),
            'survey.qmd': this.generateSurveyQmd(),
            'app.R': this.generateAppR(),
        };
    }

    // ── Available languages ──────────────────────────────────────────

    static getLanguages(osdData) {
        return Object.keys(osdData.translations || {});
    }
}

// Export for both browser and Node.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = OSD2Surveydown;
}
