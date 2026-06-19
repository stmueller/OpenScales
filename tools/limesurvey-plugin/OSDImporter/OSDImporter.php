<?php
/**
 * OSDImporter — LimeSurvey plugin to import OpenScales OSD files.
 *
 * Adds an "Import OSD" page to the LimeSurvey admin menu that accepts an
 * .osd file upload and converts it to a LimeSurvey survey programmatically,
 * with full support for sliders (VAS), array questions (Likert), parameter
 * substitution, and multi-language surveys.
 *
 * @author  OpenScales Project <shanem@mtu.edu>
 * @link    https://openscales.net
 * Compatible with LimeSurvey 6.x / PHP 8.x.
 */
class OSDImporter extends PluginBase
{
    protected $storage = 'DbStorage';
    static protected $name = 'OSDImporter';
    static protected $description = 'Import OpenScales Definition (.osd) files as LimeSurvey surveys';

    protected $settings = [];

    public $allowedPublicMethods = ['index', 'import'];

    public function init()
    {
        $this->subscribe('beforeAdminMenuRender');
        $this->subscribe('newDirectRequest');
    }

    // ------------------------------------------------------------------ Menu

    public function beforeAdminMenuRender()
    {
        $event = $this->getEvent();
        $url = $this->api->createUrl(
            'admin/pluginhelper/sa/fullpagewrapper/plugin/OSDImporter/method/index', []
        );
        $menuItem = new \LimeSurvey\Menu\MenuItem([
            'isDivider'   => false,
            'label'       => 'Import OSD',
            'href'        => $url,
            'iconClass'   => 'ri-file-upload-line',
        ]);
        $menu = new \LimeSurvey\Menu\Menu([
            'isDropDown'      => false,
            'label'           => 'Import OSD',
            'href'            => $url,
            'menuItems'       => [$menuItem],
            'iconClass'       => 'ri-file-upload-line',
            'isInMiddleSection' => false,
        ]);
        $event->append('extraMenus', [$menu]);
    }

    public function newDirectRequest()
    {
        $event = $this->getEvent();
        if ($event->get('target') !== 'OSDImporter') {
            return;
        }
        $fn = $event->get('function');
        if (method_exists($this, $fn)) {
            $this->$fn();
        }
    }

    // ------------------------------------------------------------------ Pages

    /** Main upload form. */
    public function index()
    {
        $csrfToken  = Yii::app()->request->csrfToken;
        $csrfName   = Yii::app()->request->csrfTokenName;
        $actionUrl  = $this->api->createUrl(
            'admin/pluginhelper/sa/ajax/plugin/OSDImporter/method/import', []
        );
        $html = $this->renderView('index', [
            'actionUrl' => $actionUrl,
            'csrfName'  => $csrfName,
            'csrfToken' => $csrfToken,
            'message'   => Yii::app()->user->getFlash('osd_message'),
            'error'     => Yii::app()->user->getFlash('osd_error'),
        ]);
        return $html;
    }

    /** Handle OSD file upload and create survey. */
    public function import()
    {
        if (!Yii::app()->request->isPostRequest) {
            $this->redirect('index');
            return;
        }

        $file = CUploadedFile::getInstanceByName('osd_file');
        if (!$file || $file->getError() !== UPLOAD_ERR_OK) {
            echo json_encode(['error' => 'No file uploaded or upload error.']);
            return;
        }

        $ext = strtolower(pathinfo($file->name, PATHINFO_EXTENSION));
        if ($ext !== 'osd') {
            echo json_encode(['error' => 'File must have .osd extension.']);
            return;
        }

        $raw = file_get_contents($file->tempName);
        $osd = json_decode($raw, true);
        if (!$osd) {
            echo json_encode(['error' => 'Invalid JSON in OSD file.']);
            return;
        }

        // Collect parameter overrides from POST
        $params = [];
        foreach (($_POST['params'] ?? []) as $k => $v) {
            $params[trim($k)] = trim($v);
        }

        $primaryLang = trim($_POST['primary_lang'] ?? 'en') ?: 'en';
        $extraLangs  = array_filter(array_map('trim', explode(',', $_POST['extra_langs'] ?? '')));

        ob_start();
        try {
            $result   = $this->createSurveyFromOSD($osd, $primaryLang, $extraLangs, $params);
            $sid      = $result['sid'];
            $warnings = $result['warnings'];
            $url      = $this->api->createUrl('surveyAdministration/view', ['iSurveyID' => $sid]);
            $noise    = ob_get_clean();
            if ($noise) $warnings[] = 'PHP output: ' . trim($noise);
            echo json_encode([
                'success'  => true,
                'sid'      => $sid,
                'url'      => $url,
                'warnings' => $warnings,
            ]);
        } catch (\Throwable $e) {
            $noise = ob_get_clean();
            $msg   = $e->getMessage() . ' in ' . $e->getFile() . ':' . $e->getLine();
            if ($noise) $msg .= "\nPHP output: " . trim($noise);
            echo json_encode(['error' => $msg]);
        }
    }

    // ------------------------------------------------------------------ OSD → LS

    public function createSurveyFromOSD(array $osd, string $primaryLang, array $extraLangs, array $params): array
    {
        // Unwrap .osd wrapper if present
        $defn = isset($osd['definition']) ? $osd['definition'] : $osd;
        $translations = $osd['translations'] ?? [];

        $scaleInfo = $defn['scale_info'] ?? [];
        $surveyName = $scaleInfo['name'] ?? 'Imported Scale';
        $items = $defn['items'] ?? $defn['questions'] ?? [];
        $likertOpts = $defn['likert_options'] ?? [];
        $responseScales = $defn['response_scales'] ?? [];

        $langs = array_unique(array_merge([$primaryLang], $extraLangs));
        $warnings = [];

        // Apply parameter substitutions to translations
        foreach ($translations as $lang => &$trans) {
            foreach ($trans as $key => &$val) {
                foreach ($params as $pk => $pv) {
                    $val = str_replace('{' . $pk . '}', $pv, $val);
                }
            }
        }
        unset($trans, $val);

        // ---- Create survey ----
        $sid = $this->createSurveyRecord($surveyName, $primaryLang, $langs, $translations, $likertOpts, $scaleInfo);

        // ---- Groups are created lazily: one per section, or one default if no sections ----
        $groupOrder = 0;
        $gid = null; // null = no group yet

        $self = $this;
        $ensureGroup = function() use ($self, $sid, $scaleInfo, $langs, $translations, &$gid, &$groupOrder) {
            if ($gid !== null) return;
            $gid = $self->createGroup($sid, $scaleInfo['code'] ?? 'scale', '', $langs, $translations, '', $groupOrder);
            $groupOrder++;
        };

        // ---- Create questions ----
        $qOrder = 0;
        $likertBuffer = [];
        $bufferScaleKey = null;

        $flushBuffer = function() use ($self, $sid, &$gid, $langs, $translations, $defn, $likertOpts, $responseScales, &$qOrder, &$likertBuffer, &$warnings, $ensureGroup) {
            if (!$likertBuffer) return;
            $ensureGroup();
            $self->createArrayQuestion($sid, $gid, $likertBuffer, $langs, $translations, $defn, $likertOpts, $responseScales, $qOrder, $warnings);
            $qOrder++;
            $likertBuffer = [];
        };

        foreach ($items as $item) {
            $type = $item['type'] ?? 'short';

            if ($type === 'likert') {
                $sk = $this->scaleKey($item, $defn);
                if ($sk !== $bufferScaleKey) {
                    $flushBuffer();
                    $bufferScaleKey = $sk;
                }
                $likertBuffer[] = $item;
                continue;
            }

            $flushBuffer();
            $bufferScaleKey = null;

            switch ($type) {
                case 'section':
                    // Each section = new LS group (= page break)
                    $textKey = $item['text_key'] ?? $item['id'];
                    $gid = $this->createGroup($sid, $this->safeCode($item['id']), '', $langs, $translations, $textKey, $groupOrder);
                    $groupOrder++;
                    $qOrder = 0;
                    break;
                case 'inst':
                    $ensureGroup();
                    $this->createTextDisplay($sid, $gid, $item, $langs, $translations, $qOrder);
                    $qOrder++;
                    break;
                case 'multi':
                    $ensureGroup();
                    $this->createListRadio($sid, $gid, $item, $langs, $translations, $defn, $qOrder, $warnings);
                    $qOrder++;
                    break;
                case 'multicheck':
                    $ensureGroup();
                    $this->createMultipleChoice($sid, $gid, $item, $langs, $translations, $defn, $qOrder, $warnings);
                    $qOrder++;
                    break;
                case 'short':
                    $ensureGroup();
                    $this->createShortText($sid, $gid, $item, $langs, $translations, $qOrder);
                    $qOrder++;
                    break;
                case 'long':
                    $ensureGroup();
                    $this->createLongText($sid, $gid, $item, $langs, $translations, $qOrder);
                    $qOrder++;
                    break;
                case 'vas':
                    $ensureGroup();
                    $this->createSlider($sid, $gid, $item, $langs, $translations, $qOrder, $warnings);
                    $qOrder++;
                    break;
                case 'grid':
                    $ensureGroup();
                    $this->createGridArray($sid, $gid, $item, $langs, $translations, $qOrder, $warnings);
                    $qOrder++;
                    break;
                default:
                    $warnings[] = "Item '{$item['id']}' type '$type' not supported — skipped.";
            }
        }
        $flushBuffer();

        return ['sid' => $sid, 'warnings' => $warnings];
    }

    // ------------------------------------------------------------------ Survey/Group

    public function createSurveyRecord(string $name, string $primaryLang, array $langs, array $translations, array $likertOpts, array $scaleInfo): int
    {
        // Generate unique SID (Survey model has no auto-increment)
        do {
            $sid = intval(substr(str_replace('.', '', microtime(true)) . mt_rand(100, 999), -6));
            $sid = max(100000, min(999999, $sid));
        } while (Survey::model()->findByPk($sid));

        $survey = new Survey();
        $survey->sid        = $sid;
        $survey->language   = $primaryLang;
        $survey->format     = 'I';
        $survey->template   = 'inherit';
        $survey->anonymized = 'N';
        $survey->active     = 'N';
        $survey->gsid       = 1;
        $survey->startdate  = '1980-01-01 00:00:00';
        if (!$survey->save()) {
            throw new Exception('Could not create survey: ' . print_r($survey->getErrors(), true));
        }

        // Language settings (covers primary + extra langs)
        foreach ($langs as $lang) {
            $ls = new SurveyLanguageSetting();
            $ls->surveyls_survey_id  = $sid;
            $ls->surveyls_language   = $lang;
            $ls->surveyls_title      = $name;
            $ls->surveyls_description = '';
            $ls->surveyls_welcometext = '';
            $ls->surveyls_endtext     = '';
            if (!$ls->save()) {
                throw new Exception("Could not save language settings for '$lang': " . print_r($ls->getErrors(), true));
            }
        }

        return $sid;
    }

    public function createGroup(int $sid, string $code, string $desc, array $langs, array $translations, string $headKey, int $groupOrder = 0): int
    {
        $group = new QuestionGroup();
        $group->sid         = $sid;
        $group->group_order = $groupOrder;
        $group->grelevance  = '1';
        if (!$group->save()) {
            throw new Exception('Could not create question group.');
        }
        $gid = $group->gid;

        foreach ($langs as $lang) {
            $gl = new QuestionGroupL10n();
            $gl->gid         = $gid;
            $gl->language    = $lang;
            // group_name = translated section title (shown as page heading)
            $gl->group_name  = $headKey && isset($translations[$lang][$headKey])
                ? $translations[$lang][$headKey]
                : ($desc ?: $code);
            $gl->description = '';
            $gl->save();
        }
        return $gid;
    }

    // ------------------------------------------------------------------ Question helpers

    public function safeCode(string $id): string
    {
        $code = preg_replace('/[^a-zA-Z0-9]/', '', $id);
        return substr($code, 0, 20);
    }

    public function getText(array $trans, string $key, string $fallback = ''): string
    {
        return $trans[$key] ?? $fallback;
    }

    public function scaleKey(array $item, array $defn): string
    {
        $rsId = $item['response_scale'] ?? null;
        if ($rsId) return 'rs:' . $rsId;
        $lo = $defn['likert_options'] ?? [];
        return 'lo:' . ($lo['points'] ?? 5) . ':' . ($lo['min'] ?? 1) . ':' . implode(',', $lo['labels'] ?? []);
    }

    public function getLikertPairs(array $item, array $defn): array
    {
        $rsId = $item['response_scale'] ?? null;
        $eff  = $rsId && isset($defn['response_scales'][$rsId])
            ? $defn['response_scales'][$rsId]
            : ($defn['likert_options'] ?? []);

        $points    = $item['likert_points'] ?? $eff['points'] ?? 5;
        $min       = $item['likert_min']    ?? $eff['min']    ?? 1;
        $labelKeys = $item['likert_labels'] ?? $eff['labels'] ?? [];
        while (count($labelKeys) < $points) $labelKeys[] = null;
        $pairs = [];
        for ($i = 0; $i < $points; $i++) {
            $pairs[] = [$min + $i, $labelKeys[$i]];
        }
        return $pairs;
    }

    public function saveQuestion(array $data): int
    {
        $q = new Question();
        foreach ($data as $k => $v) $q->$k = $v;
        if (!$q->save()) {
            throw new Exception("Could not save question '{$data['title']}': " . print_r($q->getErrors(), true));
        }
        return $q->qid;
    }

    public function saveL10n(int $qid, string $lang, string $text, string $help = ''): void
    {
        $l = new QuestionL10n();
        $l->qid      = $qid;
        $l->language = $lang;
        $l->question = $text;
        $l->help     = $help;
        $l->save();
    }

    public function saveAnswer(int $qid, int $sid, string $code, int $sortOrder, string $lang, string $text, int $scaleId = 0, int $assessVal = 0): void
    {
        static $answerMap = [];
        $mapKey = $qid . ':' . $code . ':' . $scaleId;
        if (!isset($answerMap[$mapKey])) {
            $a = new Answer();
            $a->qid              = $qid;
            $a->code             = $code;
            $a->sortorder        = $sortOrder;
            $a->scale_id         = $scaleId;
            $a->assessment_value = $assessVal;
            if (!$a->save()) {
                throw new Exception("Could not save answer '$code': " . print_r($a->getErrors(), true));
            }
            $answerMap[$mapKey] = $a->aid;
        }
        $l = new AnswerL10n();
        $l->aid      = $answerMap[$mapKey];
        $l->language = $lang;
        $l->answer   = $text;
        if (!$l->save()) {
            throw new Exception("Could not save answer L10n '$code'/'$lang': " . print_r($l->getErrors(), true));
        }
    }

    public function saveSubquestion(int $parentQid, int $sid, int $gid, string $code, int $order, string $lang, string $text): int
    {
        static $sqMap = [];
        $mapKey = $parentQid . ':' . $code;
        if (!isset($sqMap[$mapKey])) {
            $sq = new Question();
            $sq->sid        = $sid;
            $sq->gid        = $gid;
            $sq->parent_qid = $parentQid;
            $sq->type       = 'T';
            $sq->title      = $this->safeCode($code);
            $sq->question_order = $order;
            $sq->mandatory  = 'N';
            $sq->scale_id   = 0;
            $sq->same_default = 0;
            $sq->relevance  = '1';
            if (!$sq->save()) {
                throw new Exception("Could not save subquestion '$code'.");
            }
            $sqMap[$mapKey] = $sq->qid;
        }
        $sqid = $sqMap[$mapKey];
        $l = new QuestionL10n();
        $l->qid = $sqid; $l->language = $lang; $l->question = $text; $l->help = '';
        $l->save();
        return $sqid;
    }

    public function setQuestionAttribute(int $qid, string $attr, string $value): void
    {
        $qa = new QuestionAttribute();
        $qa->qid       = $qid;
        $qa->attribute = $attr;
        $qa->value     = $value;
        $qa->language  = '';
        $qa->save();
    }

    // ------------------------------------------------------------------ Question creators

    public function createTextDisplay(int $sid, int $gid, array $item, array $langs, array $translations, int $order): void
    {
        $code = $this->safeCode($item['id']);
        $qid  = $this->saveQuestion([
            'sid' => $sid, 'gid' => $gid, 'parent_qid' => 0,
            'type' => 'X', 'title' => $code,
            'question_order' => $order, 'mandatory' => 'N',
            'relevance' => '1', 'scale_id' => 0, 'same_default' => 0,
        ]);
        $textKey = $item['text_key'] ?? $item['id'];
        foreach ($langs as $lang) {
            $trans = $translations[$lang] ?? [];
            $this->saveL10n($qid, $lang, $trans[$textKey] ?? '');
        }
    }

    public function createListRadio(int $sid, int $gid, array $item, array $langs, array $translations, array $defn, int $order, array &$warnings): void
    {
        $code    = $this->safeCode($item['id']);
        $textKey = $item['text_key'] ?? $item['id'];
        $qid     = $this->saveQuestion([
            'sid' => $sid, 'gid' => $gid, 'parent_qid' => 0,
            'type' => 'L', 'title' => $code,
            'question_order' => $order, 'mandatory' => ($item['required'] ?? false) ? 'Y' : 'N',
            'relevance' => $this->relevance($item['visible_when'] ?? null),
            'scale_id' => 0, 'same_default' => 0,
        ]);
        foreach ($langs as $lang) {
            $trans = $translations[$lang] ?? [];
            $this->saveL10n($qid, $lang, $trans[$textKey] ?? $item['id']);
        }
        // Answers
        foreach ($item['options'] ?? [] as $i => $opt) {
            $optKey  = is_array($opt) ? ($opt['text_key'] ?? $opt['value'] ?? "A{$i}") : $opt;
            $optCode = is_array($opt) ? ($opt['value'] ?? "A{$i}") : "A{$i}";
            foreach ($langs as $lang) {
                $trans = $translations[$lang] ?? [];
                $text  = is_string($optKey) ? ($trans[$optKey] ?? $optKey) : (string)$optKey;
                $this->saveAnswer($qid, $sid, $optCode, $i, $lang, $text);
            }
        }
    }

    public function createMultipleChoice(int $sid, int $gid, array $item, array $langs, array $translations, array $defn, int $order, array &$warnings): void
    {
        $code    = $this->safeCode($item['id']);
        $textKey = $item['text_key'] ?? $item['id'];
        $qid     = $this->saveQuestion([
            'sid' => $sid, 'gid' => $gid, 'parent_qid' => 0,
            'type' => 'M', 'title' => $code,
            'question_order' => $order, 'mandatory' => ($item['required'] ?? false) ? 'Y' : 'N',
            'relevance' => $this->relevance($item['visible_when'] ?? null),
            'scale_id' => 0, 'same_default' => 0,
        ]);
        foreach ($langs as $lang) {
            $trans = $translations[$lang] ?? [];
            $this->saveL10n($qid, $lang, $trans[$textKey] ?? $item['id']);
        }
        foreach ($item['options'] ?? [] as $i => $opt) {
            $optKey = is_array($opt) ? ($opt['text_key'] ?? "SQ{$i}") : $opt;
            $sqCode = "SQ" . str_pad($i + 1, 3, '0', STR_PAD_LEFT);
            foreach ($langs as $lang) {
                $trans = $translations[$lang] ?? [];
                $text  = is_string($optKey) ? ($trans[$optKey] ?? $optKey) : (string)$optKey;
                $this->saveSubquestion($qid, $sid, $gid, $sqCode, $i, $lang, $text);
            }
        }
    }

    public function createShortText(int $sid, int $gid, array $item, array $langs, array $translations, int $order): void
    {
        $code    = $this->safeCode($item['id']);
        $textKey = $item['text_key'] ?? $item['id'];
        $qid     = $this->saveQuestion([
            'sid' => $sid, 'gid' => $gid, 'parent_qid' => 0,
            'type' => 'S', 'title' => $code,
            'question_order' => $order, 'mandatory' => ($item['required'] ?? false) ? 'Y' : 'N',
            'relevance' => $this->relevance($item['visible_when'] ?? null),
            'scale_id' => 0, 'same_default' => 0,
        ]);
        foreach ($langs as $lang) {
            $trans = $translations[$lang] ?? [];
            $this->saveL10n($qid, $lang, $trans[$textKey] ?? $item['id']);
        }
    }

    public function createLongText(int $sid, int $gid, array $item, array $langs, array $translations, int $order): void
    {
        $code    = $this->safeCode($item['id']);
        $textKey = $item['text_key'] ?? $item['id'];
        $qid     = $this->saveQuestion([
            'sid' => $sid, 'gid' => $gid, 'parent_qid' => 0,
            'type' => 'T', 'title' => $code,
            'question_order' => $order, 'mandatory' => ($item['required'] ?? false) ? 'Y' : 'N',
            'relevance' => $this->relevance($item['visible_when'] ?? null),
            'scale_id' => 0, 'same_default' => 0,
        ]);
        foreach ($langs as $lang) {
            $trans = $translations[$lang] ?? [];
            $this->saveL10n($qid, $lang, $trans[$textKey] ?? $item['id']);
        }
    }

    public function createSlider(int $sid, int $gid, array $item, array $langs, array $translations, int $order, array &$warnings): void
    {
        $code    = $this->safeCode($item['id']);
        $textKey = $item['text_key'] ?? $item['id'];
        $min     = $item['min'] ?? $item['min_value'] ?? 0;
        $max     = $item['max'] ?? $item['max_value'] ?? 100;
        $orient  = ($item['orientation'] ?? 'horizontal') === 'vertical' ? 1 : 0;

        // Resolve min/max labels from anchors or explicit keys
        $minLabelsByLang = [];
        $maxLabelsByLang = [];
        foreach ($langs as $lang) {
            $trans = $translations[$lang] ?? [];
            $minL = '';
            $maxL = '';
            if (isset($item['min_label'])) {
                $minL = $trans[$item['min_label']] ?? $item['min_label'];
            }
            if (isset($item['max_label'])) {
                $maxL = $trans[$item['max_label']] ?? $item['max_label'];
            }
            if (isset($item['anchors']) && is_array($item['anchors'])) {
                $anchors = $item['anchors'];
                $resolve = function($anchor) use ($trans) {
                    $key = is_array($anchor) ? ($anchor['label'] ?? null) : $anchor;
                    return $key ? ($trans[$key] ?? $key) : '';
                };
                if (!empty($anchors)) $minL = $resolve($anchors[0]);
                if (count($anchors) > 1) $maxL = $resolve($anchors[count($anchors) - 1]);
            }
            $minLabelsByLang[$lang] = $minL;
            $maxLabelsByLang[$lang] = $maxL;
        }

        // Type K (Multiple Numerical) with slider_layout=1 renders as a real slider.
        // A single VAS item = one K question with one subquestion (the question text as SQ).
        $qid = $this->saveQuestion([
            'sid' => $sid, 'gid' => $gid, 'parent_qid' => 0,
            'type' => 'K', 'title' => $code,
            'question_order' => $order, 'mandatory' => ($item['required'] ?? false) ? 'Y' : 'N',
            'relevance' => $this->relevance($item['visible_when'] ?? null),
            'scale_id' => 0, 'same_default' => 0,
        ]);

        // Parent question text is blank; the item text goes on the subquestion
        foreach ($langs as $lang) {
            $this->saveL10n($qid, $lang, '', '');
        }

        // One subquestion carrying the item text
        $sqCode = $code . 'sq';
        foreach ($langs as $lang) {
            $trans = $translations[$lang] ?? [];
            $text  = $trans[$textKey] ?? $item['id'];
            $help  = trim(($minLabelsByLang[$lang] ?? '') .
                (($minLabelsByLang[$lang] && $maxLabelsByLang[$lang]) ? ' | ' : '') .
                ($maxLabelsByLang[$lang] ?? ''));
            $this->saveSubquestion($qid, $sid, $gid, $sqCode, 0, $lang, $text);
            // Update help on the subquestion L10n row
            QuestionL10n::model()->updateAll(
                ['help' => $help],
                'qid = (SELECT qid FROM {{questions}} WHERE parent_qid = :p AND title = :t LIMIT 1) AND language = :l',
                [':p' => $qid, ':t' => substr($sqCode, 0, 20), ':l' => $lang]
            );
        }

        // Slider attributes on the parent question
        $this->setQuestionAttribute($qid, 'slider_layout', '1');
        $this->setQuestionAttribute($qid, 'slider_min', (string)$min);
        $this->setQuestionAttribute($qid, 'slider_max', (string)$max);
        $this->setQuestionAttribute($qid, 'slider_accuracy', '1');
        $this->setQuestionAttribute($qid, 'slider_orientation', (string)$orient);
        $this->setQuestionAttribute($qid, 'slider_showminmax', '1');
        $this->setQuestionAttribute($qid, 'slider_default_set', '0');
    }

    public function createArrayQuestion(int $sid, int $gid, array $block, array $langs, array $translations, array $defn, array $likertOpts, array $responseScales, int $order, array &$warnings): void
    {
        $firstItem = $block[0];
        $code = 'arr' . $this->safeCode($firstItem['id']);
        $code = substr($code, 0, 20);

        $mandatory = false;
        foreach ($block as $item) {
            if ($item['required'] ?? false) { $mandatory = true; break; }
        }

        $qid = $this->saveQuestion([
            'sid' => $sid, 'gid' => $gid, 'parent_qid' => 0,
            'type' => 'F', 'title' => $code,
            'question_order' => $order, 'mandatory' => $mandatory ? 'Y' : 'N',
            'relevance' => '1', 'scale_id' => 0, 'same_default' => 0,
        ]);
        foreach ($langs as $lang) {
            $this->saveL10n($qid, $lang, '');
        }

        // Subquestions (rows)
        foreach ($block as $sqIdx => $item) {
            $sqCode  = $this->safeCode($item['id']);
            $textKey = $item['text_key'] ?? $item['id'];
            foreach ($langs as $lang) {
                $trans = $translations[$lang] ?? [];
                $text  = strip_tags($trans[$textKey] ?? $item['id']);
                $this->saveSubquestion($qid, $sid, $gid, $sqCode, $sqIdx, $lang, $text);
            }
        }

        // Answers (columns) — from first item's scale
        $pairs = $this->getLikertPairs($firstItem, $defn);
        foreach ($pairs as $aIdx => [$val, $labelKey]) {
            $aCode = 'A' . str_pad($val, 3, '0', STR_PAD_LEFT);
            foreach ($langs as $lang) {
                $trans = $translations[$lang] ?? [];
                $text  = ($labelKey && isset($trans[$labelKey])) ? $trans[$labelKey] : (string)$val;
                $this->saveAnswer($qid, $sid, $aCode, $aIdx, $lang, $text, 0, $val);
            }
        }
    }

    public function createGridArray(int $sid, int $gid, array $item, array $langs, array $translations, int $order, array &$warnings): void
    {
        $code    = $this->safeCode($item['id']);
        $textKey = $item['text_key'] ?? $item['id'];
        $qid     = $this->saveQuestion([
            'sid' => $sid, 'gid' => $gid, 'parent_qid' => 0,
            'type' => 'F', 'title' => $code,
            'question_order' => $order, 'mandatory' => ($item['required'] ?? false) ? 'Y' : 'N',
            'relevance' => '1', 'scale_id' => 0, 'same_default' => 0,
        ]);
        foreach ($langs as $lang) {
            $trans = $translations[$lang] ?? [];
            $this->saveL10n($qid, $lang, $trans[$textKey] ?? $item['id']);
        }
        foreach ($item['rows'] ?? [] as $ri => $rowKey) {
            $sqCode = 'SQ' . str_pad($ri + 1, 3, '0', STR_PAD_LEFT);
            foreach ($langs as $lang) {
                $trans = $translations[$lang] ?? [];
                $this->saveSubquestion($qid, $sid, $gid, $sqCode, $ri, $lang, $trans[$rowKey] ?? $rowKey);
            }
        }
        foreach ($item['columns'] ?? [] as $ci => $colKey) {
            $aCode = 'A' . str_pad($ci + 1, 3, '0', STR_PAD_LEFT);
            foreach ($langs as $lang) {
                $trans = $translations[$lang] ?? [];
                $this->saveAnswer($qid, $sid, $aCode, $ci, $lang, $trans[$colKey] ?? $colKey);
            }
        }
    }

    // ------------------------------------------------------------------ Visibility

    public function relevance(?array $visibleWhen): string
    {
        if (!$visibleWhen) return '1';
        if (isset($visibleWhen['all'])) {
            $parts = array_map([$this, 'condToEM'], $visibleWhen['all']);
            return '(' . implode(' and ', $parts) . ')';
        }
        if (isset($visibleWhen['any'])) {
            $parts = array_map([$this, 'condToEM'], $visibleWhen['any']);
            return '(' . implode(' or ', $parts) . ')';
        }
        return $this->condToEM($visibleWhen);
    }

    public function condToEM(array $cond): string
    {
        // source: 'item', 'question', or 'parameter' key
        $src = $cond['item'] ?? $cond['question'] ?? $cond['parameter'] ?? $cond['source_name'] ?? '?';
        $src = $this->safeCode((string)$src);
        $op  = $cond['operator'] ?? $cond['op'] ?? 'equals';

        // is_answered: just check the variable is not empty
        if ($op === 'is_answered') {
            return "!is_empty({" . $src . "})";
        }

        $val = $cond['value'] ?? '';

        // 'in' operator with array value: expand to OR chain
        if ($op === 'in' && is_array($val)) {
            $parts = array_map(function($v) use ($src) {
                $vs = is_numeric($v) ? $v : '"' . $v . '"';
                return "{" . $src . "} == $vs";
            }, $val);
            return '(' . implode(' or ', $parts) . ')';
        }
        if ($op === 'not_in' && is_array($val)) {
            $parts = array_map(function($v) use ($src) {
                $vs = is_numeric($v) ? $v : '"' . $v . '"';
                return "{" . $src . "} != $vs";
            }, $val);
            return '(' . implode(' and ', $parts) . ')';
        }

        $opMap  = ['equals' => '==', 'not_equals' => '!=', 'greater_than' => '>', 'less_than' => '<',
                   'gte' => '>=', 'lte' => '<=', '==' => '==', '!=' => '!='];
        $emOp   = $opMap[$op] ?? '==';
        $valStr = is_numeric($val) ? $val : '"' . addslashes((string)$val) . '"';
        return "{" . $src . "} $emOp $valStr";
    }

    // ------------------------------------------------------------------ View

    public function renderView(string $name, array $data = []): string
    {
        $viewFile = __DIR__ . '/views/' . $name . '.php';
        extract($data);
        ob_start();
        include $viewFile;
        return ob_get_clean();
    }

    public function redirect(string $method): void
    {
        $url = $this->api->createUrl(
            'admin/pluginhelper/sa/fullpagewrapper/plugin/OSDImporter/method/' . $method, []
        );
        Yii::app()->controller->redirect($url);
    }
}
