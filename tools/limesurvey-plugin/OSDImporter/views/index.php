<?php
/** @var string $actionUrl */
/** @var string $csrfName */
/** @var string $csrfToken */
/** @var string|null $message */
/** @var string|null $error */
?>
<div class="container-fluid" id="osd-importer">
    <div class="row">
        <div class="col-md-8 col-md-offset-2">
            <h2>Import OpenScales Definition (.osd)</h2>
            <p class="text-muted">
                Upload an <strong>.osd</strong> file to create a new LimeSurvey survey.
                The scale's items, translations, and response options are imported automatically.
                Scoring and conditional logic must be configured manually.
            </p>

            <div id="osd-alert" class="hidden"></div>
            <?php if ($error): ?>
            <div class="alert alert-danger"><?= htmlspecialchars($error) ?></div>
            <?php endif; ?>
            <?php if ($message): ?>
            <div class="alert alert-success"><?= htmlspecialchars($message) ?></div>
            <?php endif; ?>

            <form id="osd-form" enctype="multipart/form-data">
                <input type="hidden" name="<?= htmlspecialchars($csrfName) ?>" value="<?= htmlspecialchars($csrfToken) ?>">

                <div class="panel panel-default">
                    <div class="panel-heading"><strong>OSD File</strong></div>
                    <div class="panel-body">
                        <div class="form-group">
                            <label for="osd_file">Select .osd file</label>
                            <input type="file" name="osd_file" id="osd_file" accept=".osd,.json" required class="form-control">
                        </div>
                        <div class="form-group">
                            <label for="primary_lang">Primary language code</label>
                            <input type="text" name="primary_lang" id="primary_lang" value="en" class="form-control" placeholder="e.g. en, de, fr, tr">
                        </div>
                        <div class="form-group">
                            <label for="extra_langs">Additional languages (comma-separated)</label>
                            <input type="text" name="extra_langs" id="extra_langs" class="form-control" placeholder="e.g. tr, de">
                        </div>
                    </div>
                </div>

                <div class="panel panel-default" id="osd-params-panel" style="display:none;">
                    <div class="panel-heading"><strong>Parameter Substitution</strong></div>
                    <div class="panel-body">
                        <p class="text-muted small">
                            This scale defines parameters (e.g. <code>{study_name}</code>).
                            Set values below to substitute them into question text.
                        </p>
                        <div id="osd-params-fields"></div>
                        <button type="button" class="btn btn-xs btn-default" id="osd-add-param">+ Add parameter</button>
                    </div>
                </div>

                <button type="submit" class="btn btn-primary" id="osd-submit">
                    <i class="ri-file-upload-line"></i> Import Survey
                </button>
            </form>

            <div id="osd-result" class="hidden" style="margin-top:20px;"></div>
        </div>
    </div>
</div>

<script>
(function() {
    var form    = document.getElementById('osd-form');
    var fileIn  = document.getElementById('osd_file');
    var submit  = document.getElementById('osd-submit');
    var result  = document.getElementById('osd-result');
    var alert   = document.getElementById('osd-alert');
    var paramsP = document.getElementById('osd-params-panel');
    var paramsFlds = document.getElementById('osd-params-fields');
    var addParam   = document.getElementById('osd-add-param');
    var actionUrl  = <?= json_encode($actionUrl) ?>;

    // Pre-scan .osd file for parameters block when selected
    fileIn.addEventListener('change', function() {
        var file = this.files[0];
        if (!file) { paramsP.style.display = 'none'; return; }
        var reader = new FileReader();
        reader.onload = function(e) {
            try {
                var osd = JSON.parse(e.target.result);
                var defn = osd.definition || osd;
                var params = defn.parameters || {};
                var keys = Object.keys(params);
                if (keys.length === 0) { paramsP.style.display = 'none'; return; }
                paramsFlds.innerHTML = '';
                keys.forEach(function(k) {
                    var p = params[k];
                    var row = document.createElement('div');
                    row.className = 'form-group';
                    row.innerHTML =
                        '<label>' + escHtml(k) +
                        (p.description ? ' <small class="text-muted">(' + escHtml(p.description) + ')</small>' : '') +
                        '</label>' +
                        '<input type="text" name="params[' + escHtml(k) + ']" class="form-control" placeholder="' + escHtml(p.default || '') + '">';
                    paramsFlds.appendChild(row);
                });
                paramsP.style.display = 'block';
            } catch(ex) {
                paramsP.style.display = 'none';
            }
        };
        reader.readAsText(file);
    });

    addParam.addEventListener('click', function() {
        var k = prompt('Parameter name (without curly braces):');
        if (!k) return;
        var row = document.createElement('div');
        row.className = 'form-group';
        row.innerHTML = '<label>' + escHtml(k) + '</label>' +
            '<input type="text" name="params[' + escHtml(k) + ']" class="form-control">';
        paramsFlds.appendChild(row);
        paramsP.style.display = 'block';
    });

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        submit.disabled = true;
        submit.innerHTML = '<i class="ri-loader-line"></i> Importing…';
        alert.className = 'hidden';
        result.className = 'hidden';

        var fd = new FormData(form);
        fetch(actionUrl, { method: 'POST', body: fd, credentials: 'same-origin' })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                submit.disabled = false;
                submit.innerHTML = '<i class="ri-file-upload-line"></i> Import Survey';
                if (data.error) {
                    alert.className = 'alert alert-danger';
                    alert.textContent = data.error;
                    return;
                }
                var html = '<div class="alert alert-success">' +
                    '<strong>Survey created!</strong> SID: ' + data.sid + ' — ' +
                    '<a href="' + escHtml(data.url) + '" class="alert-link">Open survey</a>' +
                    '</div>';
                if (data.warnings && data.warnings.length) {
                    html += '<div class="alert alert-warning"><strong>Warnings:</strong><ul>';
                    data.warnings.forEach(function(w) {
                        html += '<li>' + escHtml(w) + '</li>';
                    });
                    html += '</ul></div>';
                }
                result.innerHTML = html;
                result.className = '';
            })
            .catch(function(err) {
                submit.disabled = false;
                submit.innerHTML = '<i class="ri-file-upload-line"></i> Import Survey';
                alert.className = 'alert alert-danger';
                alert.textContent = 'Network error: ' + err.message;
            });
    });

    function escHtml(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
})();
</script>
