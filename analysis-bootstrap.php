<?php
/**
 * Shared bootstrap for static analysis (PHPStan `bootstrapFiles`, Psalm `autoloader`).
 *
 * Two dependencies we analyse against declare no Composer `autoload` section,
 * so their symbols are invisible to the analysers unless loaded explicitly:
 *
 *  - nextcloud/ocp ships the OCP/NCU API as analysis stubs only.
 *  - squizlabs/php_codesniffer ships its own autoloader, and defines its
 *    custom `T_*` token constants at runtime via `define()` inside
 *    src/Util/Tokens.php. Touching the Tokens class forces that file to load
 *    so the constants exist during analysis.
 *
 * Without this file PHPStan reports 52 errors and Psalm 19 — all of them
 * "unknown class / undefined constant" noise from the missing symbol sources,
 * not defects. Supplying the symbols is the fix; suppressing them would hide
 * real findings behind the same rule names.
 *
 * @license EUPL-1.2
 * @copyright Conduction b.v.
 */

$autoloader = require __DIR__ . '/vendor/autoload.php';
$autoloader->addPsr4('OCP\\', __DIR__ . '/vendor/nextcloud/ocp/OCP/');
$autoloader->addPsr4('NCU\\', __DIR__ . '/vendor/nextcloud/ocp/NCU/');

require_once __DIR__ . '/vendor/squizlabs/php_codesniffer/autoload.php';
class_exists('PHP_CodeSniffer\Util\Tokens');
