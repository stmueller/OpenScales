<?php
/**
 * collect.php — Minimal data collection endpoint for OpenScales Runner
 *
 * Accepts POST from scale-runner.js and writes:
 *   data/{scale}/{participant}-{timestamp}.csv   individual trial data
 *   data/{scale}/pooled.csv                      appended pooled line
 *                                                (header written on first record)
 *
 * No auth required — delegate to HTTP server auth (.htaccess) if needed.
 * Works on any PHP shared host (PHP 7.4+).
 *
 * POST fields (sent by scale-runner.js):
 *   participant   — participant ID
 *   scale         — scale code
 *   token         — peblhub token (ignored here; accepted for compat)
 *   data          — individual CSV file (multipart file upload)
 *   pooled        — pooled CSV line (string)
 *   pooled_header — pooled CSV header (string)
 */

// ── CORS (allow any origin; restrict in production) ──────────
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

// ── Only accept POST ─────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

// ── Helpers ──────────────────────────────────────────────────
function sanitize_filename(string $s): string {
    // Allow alphanumeric, dash, underscore, dot — remove everything else
    return preg_replace('/[^A-Za-z0-9._\-]/', '_', $s);
}

function json_response(int $code, array $body): void {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($body);
    exit;
}

// ── Read fields ───────────────────────────────────────────────
$participant = isset($_POST['participant']) ? trim($_POST['participant']) : '';
$scale       = isset($_POST['scale'])       ? trim($_POST['scale'])       : '';
$pooled      = isset($_POST['pooled'])      ? $_POST['pooled']            : '';
$pooledHdr   = isset($_POST['pooled_header']) ? $_POST['pooled_header']   : '';

if ($scale === '' || $participant === '') {
    json_response(400, ['error' => 'Missing required fields: scale, participant']);
}

$scale       = sanitize_filename($scale);
$participant = sanitize_filename($participant);

// ── Data directory ────────────────────────────────────────────
$dataRoot = __DIR__ . '/data/' . $scale . '/' . $participant;
if (!is_dir($dataRoot)) {
    if (!mkdir($dataRoot, 0755, true)) {
        json_response(500, ['error' => 'Cannot create data directory']);
    }
}

// ── Write individual CSV ──────────────────────────────────────
$savedIndividual = false;
if (isset($_FILES['data']) && $_FILES['data']['error'] === UPLOAD_ERR_OK) {
    $ts            = date('YmdHis');
    $origName      = isset($_FILES['data']['name']) ? $_FILES['data']['name'] : '';
    $origName      = sanitize_filename($origName);
    // Use original filename if present, otherwise fall back to timestamped CSV
    $filename = $origName !== '' ? $origName : "{$participant}-{$ts}.csv";
    // Avoid collisions: insert timestamp before extension if file already exists
    if (file_exists($dataRoot . '/' . $filename)) {
        $ext      = pathinfo($filename, PATHINFO_EXTENSION);
        $base     = pathinfo($filename, PATHINFO_FILENAME);
        $filename = "{$base}-{$ts}" . ($ext !== '' ? ".{$ext}" : '');
    }
    $dest     = $dataRoot . '/' . $filename;
    if (move_uploaded_file($_FILES['data']['tmp_name'], $dest)) {
        chmod($dest, 0644);
        $savedIndividual = true;
    } else {
        json_response(500, ['error' => 'Failed to save individual CSV']);
    }
}

// ── Append to pooled CSV ──────────────────────────────────────
$savedPooled = false;
if ($pooled !== '') {
    $scaleDir   = __DIR__ . '/data/' . $scale;
    $pooledFile = $scaleDir . '/pooled.csv';
    $newFile    = !file_exists($pooledFile);

    $fh = fopen($pooledFile, 'a');
    if ($fh === false) {
        json_response(500, ['error' => 'Cannot open pooled CSV for writing']);
    }
    if ($newFile && $pooledHdr !== '') {
        fwrite($fh, $pooledHdr . "\r\n");
    }
    fwrite($fh, $pooled . "\r\n");
    fclose($fh);
    if ($newFile) chmod($pooledFile, 0644);
    $savedPooled = true;
}

// ── Success ───────────────────────────────────────────────────
json_response(200, [
    'ok'              => true,
    'individual_saved' => $savedIndividual,
    'pooled_saved'    => $savedPooled,
]);
