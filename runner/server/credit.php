<?php
/**
 * Test credit-granting endpoint for OpenScales chain runner.
 *
 * Simulates a Sona/MTurk/Prolific completion callback.
 * Logs the callback to a file and displays a confirmation page.
 *
 * Usage: credit.php?pid=P001&study=TEST&status=complete
 */

header('Content-Type: text/html; charset=utf-8');

$pid    = $_GET['pid']    ?? $_POST['pid']    ?? 'unknown';
$study  = $_GET['study']  ?? $_POST['study']  ?? 'unknown';
$status = $_GET['status'] ?? $_POST['status'] ?? 'unknown';
$ts     = date('c');

// Log the callback
$logDir  = __DIR__ . '/data/_credits';
if (!is_dir($logDir)) {
    mkdir($logDir, 0755, true);
}

$logFile = $logDir . '/credit_log.csv';
$isNew   = !file_exists($logFile);
$fh      = fopen($logFile, 'a');
if ($isNew) {
    fwrite($fh, "timestamp,study,pid,status\r\n");
}
fwrite($fh, "$ts,$study,$pid,$status\r\n");
fclose($fh);

// Display confirmation
$ePid    = htmlspecialchars($pid, ENT_QUOTES);
$eStudy  = htmlspecialchars($study, ENT_QUOTES);
$eStatus = htmlspecialchars($status, ENT_QUOTES);

?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Study Credit Confirmation</title>
<style>
  body {
    font-family: system-ui, -apple-system, sans-serif;
    background: #f3f4f6; margin: 0; padding: 2rem;
  }
  .card {
    max-width: 500px; margin: 3rem auto; padding: 2rem;
    background: #fff; border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,.1);
    text-align: center;
  }
  .check { font-size: 3rem; color: #16a34a; }
  h1 { font-size: 1.3rem; color: #111; margin: 0.5rem 0; }
  .detail { color: #6b7280; font-size: 0.9rem; margin-top: 1rem; }
  .detail strong { color: #374151; }
  .note {
    margin-top: 1.5rem; padding: 0.8rem;
    background: #fef3c7; border-radius: 6px;
    font-size: 0.85rem; color: #92400e;
  }
</style>
</head>
<body>
<div class="card">
  <div class="check">&#10004;</div>
  <h1>Credit Recorded</h1>
  <p class="detail">
    <strong>Study:</strong> <?= $eStudy ?><br>
    <strong>Participant:</strong> <?= $ePid ?><br>
    <strong>Status:</strong> <?= $eStatus ?><br>
    <strong>Time:</strong> <?= htmlspecialchars($ts) ?>
  </p>
  <div class="note">
    This is a <strong>test endpoint</strong>. In production, this URL would be
    replaced with your Sona, MTurk, or Prolific completion callback.
  </div>
</div>
</body>
</html>
